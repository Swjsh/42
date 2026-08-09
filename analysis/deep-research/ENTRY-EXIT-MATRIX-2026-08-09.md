# ENTRY x EXIT MATRIX -- 2026-08-09

J's `/goal`: *"dynamic entries and exit testing across our trades, map it into a multi column/row matrix table and figure out what is profitable."*

**Runtime:** 1202.0s. **Generated:** 2026-08-09T14:03:43.809072. Frozen pre-registration: [`prereg-entry-exit-matrix-2026-08-09.json`](../recommendations/prereg-entry-exit-matrix-2026-08-09.json) (commit `edc595af`, committed before the runner existed -- verified: the runner is not in that commit).

## Verdict

- **Population A** (399-day replay, 318 CONTROL binary trades): **0 of 96 cells survive BH-FDR at q=0.10** (effective p threshold None).
- **Population B** (244 real broker fills over 27 days, 2026-06-26..2026-08-07): **0 of 48 cells survive** (effective p threshold None).
- **Control cell** (as-shipped entry x as-shipped exit): population A $16.06/trade over n=289; population B $22.17/trade over n=64.

## THE MATRIX -- expectancy $/trade

Rows = entry variant. Columns = exit variant. This is the crossed table: every entry rule is priced under every exit rule, so an entry that only works under a particular exit is visible as a cell rather than hidden in a row average.

### Population A -- 399-day replay

| entry \ exit | CONTROL | TP1_30 | TP1_40 | TP1_50 | TP1_75 | MFE_TRAIL | ATR_STOP | CATCAP_25 | CATCAP_30 | CATCAP_40 | CATCAP_60 | STRUCT_ONLY |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **CONTROL** | $16.06 | $-8.71 | $2.98 | $-15.27 | $-6.29 | $18.34 | $95.26 | $0.58 | $2.63 | $14.65 | $19.72 | $39.62 |
| **STRUCT8** | $30.38 | $-8.10 | $2.62 | $0.26 | $13.51 | $34.89 | $95.87 | $0.26 | $0.96 | $23.78 | $25.67 | $57.64 |
| **VD1** | $16.67 | $-9.06 | $2.56 | $-15.97 | $-7.31 | $18.97 | $94.30 | $1.08 | $3.14 | $15.25 | $20.36 | $40.40 |
| **LADDER7** | $-7.14 | $-14.36 | $-14.33 | $-16.27 | $-11.45 | $-7.06 | $7.17 | $-7.04 | $-8.74 | $-7.66 | $-5.89 | $-2.75 |
| **LADDER8** | $-0.57 | $-11.35 | $-9.31 | $-10.84 | $-5.53 | $0.27 | $17.47 | $-1.46 | $-3.79 | $-2.34 | $0.25 | $4.62 |
| **LADDER9** | $3.86 | $-9.93 | $-8.53 | $-10.88 | $-4.83 | $5.33 | $22.16 | $5.91 | $3.77 | $3.80 | $4.46 | $9.84 |
| **MAX3** | $16.06 | $-8.71 | $2.98 | $-15.27 | $-6.29 | $18.34 | $95.26 | $0.58 | $2.63 | $14.65 | $19.72 | $39.62 |
| **ZONE** | $-4.87 | $-7.70 | $-7.76 | $-8.39 | $-5.77 | $-4.06 | $5.18 | $-5.03 | $-6.11 | $-4.86 | $-4.47 | $-1.65 |

### Population B -- real broker fills

`LADDER7/8/9` and `ZONE` are **n/a** here by construction: a realized fill carries no score/blocker/level-scan record to re-admit against. Disclosed, not silently dropped.

| entry \ exit | CONTROL | TP1_30 | TP1_40 | TP1_50 | TP1_75 | MFE_TRAIL | ATR_STOP | CATCAP_25 | CATCAP_30 | CATCAP_40 | CATCAP_60 | STRUCT_ONLY |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **CONTROL** | $22.17 | $24.30 | $18.76 | $8.10 | $16.35 | $12.36 | $57.16 | $33.59 | $30.34 | $26.67 | $20.38 | $20.75 |
| **STRUCT8** | $-25.80 | $-0.62 | $-9.17 | $-27.60 | $-24.82 | $-24.48 | $39.69 | $-8.37 | $-13.48 | $-18.41 | $-28.56 | $-27.86 |
| **VD1** | $32.48 | $36.27 | $29.71 | $16.87 | $26.12 | $20.41 | $71.37 | $46.02 | $42.17 | $37.81 | $30.36 | $30.80 |
| **MAX3** | $-33.67 | $-2.57 | $-17.08 | $-37.12 | $-33.76 | $-32.00 | $-17.97 | $-18.04 | $-20.91 | $-26.65 | $-36.47 | $-35.89 |

### Population A -- total $ (same grid, absolute dollars)

| entry \ exit | CONTROL | TP1_30 | TP1_40 | TP1_50 | TP1_75 | MFE_TRAIL | ATR_STOP | CATCAP_25 | CATCAP_30 | CATCAP_40 | CATCAP_60 | STRUCT_ONLY |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **CONTROL** | $4,641.00 | $-2,595.90 | $882.40 | $-4,488.55 | $-1,836.95 | $5,301.10 | $25,720.34 | $170.60 | $769.80 | $4,263.00 | $5,697.70 | $11,369.60 |
| **STRUCT8** | $5,497.95 | $-1,481.45 | $476.10 | $46.85 | $2,445.05 | $6,314.20 | $16,969.34 | $48.30 | $174.95 | $4,351.55 | $4,646.25 | $10,318.15 |
| **VD1** | $4,785.60 | $-2,683.20 | $751.70 | $-4,662.65 | $-2,119.55 | $5,445.70 | $25,367.34 | $315.20 | $914.40 | $4,407.60 | $5,842.30 | $11,514.20 |
| **LADDER7** | $-10,907.40 | $-26,803.15 | $-25,755.90 | $-27,795.05 | $-18,484.65 | $-10,908.70 | $7,653.01 | $-11,537.40 | $-13,926.10 | $-11,925.30 | $-8,913.35 | $-4,159.90 |
| **LADDER8** | $-708.65 | $-17,292.30 | $-13,674.95 | $-14,999.80 | $-7,253.90 | $341.30 | $15,009.42 | $-1,966.70 | $-4,936.05 | $-2,965.15 | $306.30 | $5,660.95 |
| **LADDER9** | $3,734.00 | $-11,329.50 | $-9,404.00 | $-11,464.05 | $-4,848.25 | $5,220.00 | $15,800.16 | $6,034.30 | $3,767.20 | $3,722.05 | $4,262.30 | $9,379.95 |
| **MAX3** | $4,641.00 | $-2,595.90 | $882.40 | $-4,488.55 | $-1,836.95 | $5,301.10 | $25,720.34 | $170.60 | $769.80 | $4,263.00 | $5,697.70 | $11,369.60 |
| **ZONE** | $-10,423.55 | $-19,279.35 | $-19,001.15 | $-19,877.05 | $-12,978.10 | $-8,785.00 | $7,091.23 | $-10,929.10 | $-13,232.45 | $-10,445.85 | $-9,521.30 | $-3,510.40 |

### Population A -- n (trade count per cell)

| entry \ exit | CONTROL | TP1_30 | TP1_40 | TP1_50 | TP1_75 | MFE_TRAIL | ATR_STOP | CATCAP_25 | CATCAP_30 | CATCAP_40 | CATCAP_60 | STRUCT_ONLY |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **CONTROL** | 289 | 298 | 296 | 294 | 292 | 289 | 270 | 294 | 293 | 291 | 289 | 287 |
| **STRUCT8** | 181 | 183 | 182 | 182 | 181 | 181 | 177 | 183 | 183 | 183 | 181 | 179 |
| **VD1** | 287 | 296 | 294 | 292 | 290 | 287 | 269 | 292 | 291 | 289 | 287 | 285 |
| **LADDER7** | 1,527 | 1,867 | 1,797 | 1,708 | 1,614 | 1,545 | 1,068 | 1,640 | 1,593 | 1,556 | 1,514 | 1,511 |
| **LADDER8** | 1,242 | 1,524 | 1,469 | 1,384 | 1,312 | 1,255 | 859 | 1,347 | 1,302 | 1,269 | 1,230 | 1,226 |
| **LADDER9** | 967 | 1,141 | 1,102 | 1,054 | 1,003 | 979 | 713 | 1,021 | 999 | 980 | 955 | 953 |
| **MAX3** | 289 | 298 | 296 | 294 | 292 | 289 | 270 | 294 | 293 | 291 | 289 | 287 |
| **ZONE** | 2,141 | 2,503 | 2,448 | 2,370 | 2,248 | 2,164 | 1,369 | 2,172 | 2,164 | 2,148 | 2,131 | 2,128 |

## Full per-cell battery -- every cell, no truncation

### Population A

| cell | n | days | total $ | exp $/tr | WR | drop-best exp | 1st-half | 2nd-half | stable | Tue 08-04 $ | boot p | BH q=.10 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|:-:|--:|--:|:-:|
| `CONTROL x CONTROL` | 289 | 205 | $4,641.00 | $16.06 | 24.6% | $8.43 | $14.39 | $17.81 | yes | -- | 0.3515 | no |
| `CONTROL x TP1_30` | 298 | 205 | $-2,595.90 | $-8.71 | 39.9% | $-13.84 | $-7.54 | $-9.91 | yes | -- | 0.6291 | no |
| `CONTROL x TP1_40` | 296 | 205 | $882.40 | $2.98 | 36.1% | $-2.48 | $-1.30 | $7.38 | no | -- | 0.4597 | no |
| `CONTROL x TP1_50` | 294 | 205 | $-4,488.55 | $-15.27 | 31.3% | $-22.06 | $-13.76 | $-16.82 | yes | -- | 0.6937 | no |
| `CONTROL x TP1_75` | 292 | 205 | $-1,836.95 | $-6.29 | 26.0% | $-13.06 | $-4.50 | $-8.16 | yes | -- | 0.5741 | no |
| `CONTROL x MFE_TRAIL` | 289 | 205 | $5,301.10 | $18.34 | 24.6% | $10.34 | $17.61 | $19.11 | yes | -- | 0.3322 | no |
| `CONTROL x ATR_STOP` | 270 | 205 | $25,720.34 | $95.26 | 34.8% | $84.98 | $54.91 | $138.08 | yes | -- | 0.0284 | no |
| `CONTROL x CATCAP_25` | 294 | 205 | $170.60 | $0.58 | 21.8% | $-6.97 | $8.21 | $-7.37 | no | -- | 0.4998 | no |
| `CONTROL x CATCAP_30` | 293 | 205 | $769.80 | $2.63 | 22.2% | $-4.94 | $14.28 | $-9.43 | no | -- | 0.4746 | no |
| `CONTROL x CATCAP_40` | 291 | 205 | $4,263.00 | $14.65 | 23.7% | $7.07 | $14.33 | $14.98 | yes | -- | 0.3562 | no |
| `CONTROL x CATCAP_60` | 289 | 205 | $5,697.70 | $19.72 | 24.9% | $12.10 | $27.22 | $11.84 | yes | -- | 0.3233 | no |
| `CONTROL x STRUCT_ONLY` | 287 | 205 | $11,369.60 | $39.62 | 25.4% | $32.02 | $27.22 | $52.81 | yes | -- | 0.1673 | no |
| `STRUCT8 x CONTROL` | 181 | 149 | $5,497.95 | $30.38 | 24.9% | $18.25 | $11.20 | $51.55 | yes | -- | 0.2888 | no |
| `STRUCT8 x TP1_30` | 183 | 149 | $-1,481.45 | $-8.10 | 39.9% | $-16.46 | $-34.77 | $20.70 | no | -- | 0.5837 | no |
| `STRUCT8 x TP1_40` | 182 | 149 | $476.10 | $2.62 | 35.2% | $-6.29 | $-28.91 | $37.04 | no | -- | 0.4711 | no |
| `STRUCT8 x TP1_50` | 182 | 149 | $46.85 | $0.26 | 31.9% | $-10.53 | $-24.98 | $27.81 | no | -- | 0.5023 | no |
| `STRUCT8 x TP1_75` | 181 | 149 | $2,445.05 | $13.51 | 27.1% | $2.68 | $-5.92 | $34.97 | no | -- | 0.3886 | no |
| `STRUCT8 x MFE_TRAIL` | 181 | 149 | $6,314.20 | $34.89 | 24.9% | $22.17 | $14.09 | $57.86 | yes | -- | 0.2663 | no |
| `STRUCT8 x ATR_STOP` | 177 | 149 | $16,969.34 | $95.87 | 33.9% | $80.56 | $23.96 | $173.71 | yes | -- | 0.0745 | no |
| `STRUCT8 x CATCAP_25` | 183 | 149 | $48.30 | $0.26 | 20.8% | $-11.89 | $-10.81 | $12.22 | no | -- | 0.5041 | no |
| `STRUCT8 x CATCAP_30` | 183 | 149 | $174.95 | $0.96 | 21.3% | $-11.19 | $11.35 | $-10.27 | no | -- | 0.4987 | no |
| `STRUCT8 x CATCAP_40` | 183 | 149 | $4,351.55 | $23.78 | 23.5% | $11.75 | $16.59 | $31.54 | yes | -- | 0.3379 | no |
| `STRUCT8 x CATCAP_60` | 181 | 149 | $4,646.25 | $25.67 | 24.9% | $13.52 | $11.20 | $41.65 | yes | -- | 0.3206 | no |
| `STRUCT8 x STRUCT_ONLY` | 179 | 149 | $10,318.15 | $57.64 | 25.7% | $45.54 | $11.20 | $110.16 | yes | -- | 0.1575 | no |
| `VD1 x CONTROL` | 287 | 204 | $4,785.60 | $16.67 | 24.4% | $9.00 | $14.39 | $19.10 | yes | -- | 0.3374 | no |
| `VD1 x TP1_30` | 296 | 204 | $-2,683.20 | $-9.06 | 39.9% | $-14.23 | $-7.54 | $-10.65 | yes | -- | 0.6423 | no |
| `VD1 x TP1_40` | 294 | 204 | $751.70 | $2.56 | 36.0% | $-2.95 | $-1.30 | $6.57 | no | -- | 0.4610 | no |
| `VD1 x TP1_50` | 292 | 204 | $-4,662.65 | $-15.97 | 31.2% | $-22.82 | $-13.76 | $-18.27 | yes | -- | 0.7036 | no |
| `VD1 x TP1_75` | 290 | 204 | $-2,119.55 | $-7.31 | 25.9% | $-14.13 | $-4.50 | $-10.28 | yes | -- | 0.5863 | no |
| `VD1 x MFE_TRAIL` | 287 | 204 | $5,445.70 | $18.97 | 24.4% | $10.92 | $17.61 | $20.43 | yes | -- | 0.3179 | no |
| `VD1 x ATR_STOP` | 269 | 204 | $25,367.34 | $94.30 | 34.6% | $83.98 | $54.91 | $136.42 | yes | -- | 0.0297 | no |
| `VD1 x CATCAP_25` | 292 | 204 | $315.20 | $1.08 | 21.6% | $-6.52 | $8.21 | $-6.46 | no | -- | 0.4989 | no |
| `VD1 x CATCAP_30` | 291 | 204 | $914.40 | $3.14 | 22.0% | $-4.48 | $14.28 | $-8.55 | no | -- | 0.4713 | no |
| `VD1 x CATCAP_40` | 289 | 204 | $4,407.60 | $15.25 | 23.5% | $7.62 | $14.33 | $16.22 | yes | -- | 0.3529 | no |
| `VD1 x CATCAP_60` | 287 | 204 | $5,842.30 | $20.36 | 24.7% | $12.69 | $27.22 | $13.05 | yes | -- | 0.3057 | no |
| `VD1 x STRUCT_ONLY` | 285 | 204 | $11,514.20 | $40.40 | 25.3% | $32.75 | $27.22 | $54.64 | yes | -- | 0.1681 | no |
| `LADDER7 x CONTROL` | 1527 | 356 | $-10,907.40 | $-7.14 | 30.1% | $-8.88 | $-16.50 | $1.40 | no | $-222.00 | 0.8244 | no |
| `LADDER7 x TP1_30` | 1867 | 356 | $-26,803.15 | $-14.36 | 40.1% | $-15.37 | $-14.62 | $-14.12 | yes | $-222.00 | 0.9992 | no |
| `LADDER7 x TP1_40` | 1797 | 356 | $-25,755.90 | $-14.33 | 37.3% | $-15.48 | $-18.51 | $-10.72 | yes | $-222.00 | 0.9974 | no |
| `LADDER7 x TP1_50` | 1708 | 356 | $-27,795.05 | $-16.27 | 34.6% | $-17.42 | $-18.42 | $-14.38 | yes | $-222.00 | 0.9983 | no |
| `LADDER7 x TP1_75` | 1614 | 356 | $-18,484.65 | $-11.45 | 31.8% | $-12.88 | $-18.67 | $-4.92 | yes | $-222.00 | 0.9561 | no |
| `LADDER7 x MFE_TRAIL` | 1545 | 356 | $-10,908.70 | $-7.06 | 30.1% | $-8.70 | $-15.03 | $0.15 | no | $-222.00 | 0.8150 | no |
| `LADDER7 x ATR_STOP` | 1068 | 356 | $7,653.01 | $7.17 | 34.7% | $4.73 | $-9.76 | $22.70 | no | $-222.00 | 0.2813 | no |
| `LADDER7 x CATCAP_25` | 1640 | 356 | $-11,537.40 | $-7.04 | 28.3% | $-8.65 | $-14.35 | $-0.53 | yes | $-222.00 | 0.8495 | no |
| `LADDER7 x CATCAP_30` | 1593 | 356 | $-13,926.10 | $-8.74 | 28.6% | $-10.41 | $-13.35 | $-4.64 | yes | $-222.00 | 0.8881 | no |
| `LADDER7 x CATCAP_40` | 1556 | 356 | $-11,925.30 | $-7.66 | 29.8% | $-9.37 | $-15.97 | $-0.15 | yes | $-222.00 | 0.8461 | no |
| `LADDER7 x CATCAP_60` | 1514 | 356 | $-8,913.35 | $-5.89 | 30.3% | $-7.63 | $-15.20 | $2.67 | no | $-222.00 | 0.7772 | no |
| `LADDER7 x STRUCT_ONLY` | 1511 | 356 | $-4,159.90 | $-2.75 | 30.3% | $-4.49 | $-15.68 | $9.11 | no | $-222.00 | 0.6344 | no |
| `LADDER8 x CONTROL` | 1242 | 346 | $-708.65 | $-0.57 | 29.5% | $-2.46 | $-5.65 | $4.03 | no | -- | 0.5201 | no |
| `LADDER8 x TP1_30` | 1524 | 346 | $-17,292.30 | $-11.35 | 41.1% | $-12.31 | $-5.93 | $-15.86 | yes | -- | 0.9804 | no |
| `LADDER8 x TP1_40` | 1469 | 346 | $-13,674.95 | $-9.31 | 38.4% | $-10.36 | $-7.66 | $-10.70 | yes | -- | 0.9378 | no |
| `LADDER8 x TP1_50` | 1384 | 346 | $-14,999.80 | $-10.84 | 35.1% | $-12.17 | $-8.85 | $-12.55 | yes | -- | 0.9410 | no |
| `LADDER8 x TP1_75` | 1312 | 346 | $-7,253.90 | $-5.53 | 31.6% | $-7.19 | $-7.62 | $-3.65 | yes | -- | 0.7450 | no |
| `LADDER8 x MFE_TRAIL` | 1255 | 346 | $341.30 | $0.27 | 29.6% | $-1.68 | $-4.05 | $4.15 | no | -- | 0.4922 | no |
| `LADDER8 x ATR_STOP` | 859 | 346 | $15,009.42 | $17.47 | 34.7% | $14.78 | $-1.87 | $35.05 | no | -- | 0.1201 | no |
| `LADDER8 x CATCAP_25` | 1347 | 346 | $-1,966.70 | $-1.46 | 26.7% | $-3.20 | $-3.57 | $0.37 | no | -- | 0.5722 | no |
| `LADDER8 x CATCAP_30` | 1302 | 346 | $-4,936.05 | $-3.79 | 27.6% | $-5.60 | $-3.17 | $-4.33 | yes | -- | 0.6754 | no |
| `LADDER8 x CATCAP_40` | 1269 | 346 | $-2,965.15 | $-2.34 | 28.8% | $-4.19 | $-4.87 | $-0.10 | yes | -- | 0.6020 | no |
| `LADDER8 x CATCAP_60` | 1230 | 346 | $306.30 | $0.25 | 29.6% | $-1.66 | $-4.45 | $4.53 | no | -- | 0.4915 | no |
| `LADDER8 x STRUCT_ONLY` | 1226 | 346 | $5,660.95 | $4.62 | 29.8% | $2.71 | $-4.91 | $13.31 | no | -- | 0.3209 | no |
| `LADDER9 x CONTROL` | 967 | 325 | $3,734.00 | $3.86 | 28.3% | $1.45 | $-7.41 | $14.56 | no | -- | 0.3799 | no |
| `LADDER9 x TP1_30` | 1141 | 325 | $-11,329.50 | $-9.93 | 40.8% | $-11.34 | $-7.65 | $-11.93 | yes | -- | 0.9211 | no |
| `LADDER9 x TP1_40` | 1102 | 325 | $-9,404.00 | $-8.53 | 37.2% | $-9.93 | $-8.77 | $-8.32 | yes | -- | 0.8693 | no |
| `LADDER9 x TP1_50` | 1054 | 325 | $-11,464.05 | $-10.88 | 34.2% | $-12.46 | $-8.87 | $-12.68 | yes | -- | 0.8917 | no |
| `LADDER9 x TP1_75` | 1003 | 325 | $-4,848.25 | $-4.83 | 30.3% | $-6.80 | $-10.93 | $0.81 | no | -- | 0.6835 | no |
| `LADDER9 x MFE_TRAIL` | 979 | 325 | $5,220.00 | $5.33 | 28.4% | $2.84 | $-6.27 | $16.27 | no | -- | 0.3244 | no |
| `LADDER9 x ATR_STOP` | 713 | 325 | $15,800.16 | $22.16 | 33.2% | $18.93 | $-10.70 | $54.38 | no | -- | 0.1057 | no |
| `LADDER9 x CATCAP_25` | 1021 | 325 | $6,034.30 | $5.91 | 26.2% | $3.63 | $-2.55 | $13.75 | no | -- | 0.2887 | no |
| `LADDER9 x CATCAP_30` | 999 | 325 | $3,767.20 | $3.77 | 26.9% | $1.43 | $-3.66 | $10.70 | no | -- | 0.3773 | no |
| `LADDER9 x CATCAP_40` | 980 | 325 | $3,722.05 | $3.80 | 27.7% | $1.41 | $-6.77 | $13.65 | no | -- | 0.3812 | no |
| `LADDER9 x CATCAP_60` | 955 | 325 | $4,262.30 | $4.46 | 28.2% | $2.02 | $-5.05 | $13.61 | no | -- | 0.3531 | no |
| `LADDER9 x STRUCT_ONLY` | 953 | 325 | $9,379.95 | $9.84 | 28.4% | $7.40 | $-5.66 | $24.80 | no | -- | 0.2159 | no |
| `MAX3 x CONTROL` | 289 | 205 | $4,641.00 | $16.06 | 24.6% | $8.43 | $14.39 | $17.81 | yes | -- | 0.3515 | no |
| `MAX3 x TP1_30` | 298 | 205 | $-2,595.90 | $-8.71 | 39.9% | $-13.84 | $-7.54 | $-9.91 | yes | -- | 0.6291 | no |
| `MAX3 x TP1_40` | 296 | 205 | $882.40 | $2.98 | 36.1% | $-2.48 | $-1.30 | $7.38 | no | -- | 0.4597 | no |
| `MAX3 x TP1_50` | 294 | 205 | $-4,488.55 | $-15.27 | 31.3% | $-22.06 | $-13.76 | $-16.82 | yes | -- | 0.6937 | no |
| `MAX3 x TP1_75` | 292 | 205 | $-1,836.95 | $-6.29 | 26.0% | $-13.06 | $-4.50 | $-8.16 | yes | -- | 0.5741 | no |
| `MAX3 x MFE_TRAIL` | 289 | 205 | $5,301.10 | $18.34 | 24.6% | $10.34 | $17.61 | $19.11 | yes | -- | 0.3322 | no |
| `MAX3 x ATR_STOP` | 270 | 205 | $25,720.34 | $95.26 | 34.8% | $84.98 | $54.91 | $138.08 | yes | -- | 0.0284 | no |
| `MAX3 x CATCAP_25` | 294 | 205 | $170.60 | $0.58 | 21.8% | $-6.97 | $8.21 | $-7.37 | no | -- | 0.4998 | no |
| `MAX3 x CATCAP_30` | 293 | 205 | $769.80 | $2.63 | 22.2% | $-4.94 | $14.28 | $-9.43 | no | -- | 0.4746 | no |
| `MAX3 x CATCAP_40` | 291 | 205 | $4,263.00 | $14.65 | 23.7% | $7.07 | $14.33 | $14.98 | yes | -- | 0.3562 | no |
| `MAX3 x CATCAP_60` | 289 | 205 | $5,697.70 | $19.72 | 24.9% | $12.10 | $27.22 | $11.84 | yes | -- | 0.3233 | no |
| `MAX3 x STRUCT_ONLY` | 287 | 205 | $11,369.60 | $39.62 | 25.4% | $32.02 | $27.22 | $52.81 | yes | -- | 0.1673 | no |
| `ZONE x CONTROL` | 2141 | 370 | $-10,423.55 | $-4.87 | 31.1% | $-5.89 | $-9.08 | $-0.96 | yes | $-108.00 | 0.7996 | no |
| `ZONE x TP1_30` | 2503 | 370 | $-19,279.35 | $-7.70 | 38.8% | $-8.34 | $-6.12 | $-9.20 | yes | $-108.00 | 0.9856 | no |
| `ZONE x TP1_40` | 2448 | 370 | $-19,001.15 | $-7.76 | 36.1% | $-8.49 | $-8.31 | $-7.26 | yes | $-108.00 | 0.9811 | no |
| `ZONE x TP1_50` | 2370 | 370 | $-19,877.05 | $-8.39 | 34.5% | $-9.19 | $-7.76 | $-8.97 | yes | $-108.00 | 0.9778 | no |
| `ZONE x TP1_75` | 2248 | 370 | $-12,978.10 | $-5.77 | 32.5% | $-6.62 | $-8.24 | $-3.45 | yes | $-108.00 | 0.8750 | no |
| `ZONE x MFE_TRAIL` | 2164 | 370 | $-8,785.00 | $-4.06 | 31.1% | $-5.34 | $-8.49 | $0.06 | no | $-108.00 | 0.7673 | no |
| `ZONE x ATR_STOP` | 1369 | 370 | $7,091.23 | $5.18 | 35.1% | $3.09 | $-15.20 | $24.20 | no | $-108.00 | 0.3068 | no |
| `ZONE x CATCAP_25` | 2172 | 370 | $-10,929.10 | $-5.03 | 30.7% | $-6.04 | $-9.32 | $-1.09 | yes | $-108.00 | 0.8254 | no |
| `ZONE x CATCAP_30` | 2164 | 370 | $-13,232.45 | $-6.11 | 30.7% | $-7.13 | $-8.39 | $-4.03 | yes | $-108.00 | 0.8701 | no |
| `ZONE x CATCAP_40` | 2148 | 370 | $-10,445.85 | $-4.86 | 31.0% | $-5.88 | $-8.61 | $-1.41 | yes | $-108.00 | 0.8049 | no |
| `ZONE x CATCAP_60` | 2131 | 370 | $-9,521.30 | $-4.47 | 31.1% | $-5.50 | $-7.74 | $-1.42 | yes | $-108.00 | 0.7812 | no |
| `ZONE x STRUCT_ONLY` | 2128 | 370 | $-3,510.40 | $-1.65 | 31.2% | $-2.67 | $-7.74 | $4.04 | no | $-108.00 | 0.6144 | no |

### Population B

| cell | n | days | total $ | exp $/tr | WR | drop-best exp | 1st-half | 2nd-half | stable | Tue 08-04 $ | boot p | BH q=.10 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|:-:|--:|--:|:-:|
| `CONTROL x CONTROL` | 64 | 26 | $1,418.85 | $22.17 | 18.8% | $-25.83 | $-3.96 | $57.97 | no | $3,020.20 | 0.3259 | no |
| `CONTROL x TP1_30` | 65 | 26 | $1,579.60 | $24.30 | 32.3% | $-9.58 | $-13.42 | $74.15 | no | $2,183.00 | 0.2319 | no |
| `CONTROL x TP1_40` | 64 | 26 | $1,200.80 | $18.76 | 25.0% | $-17.77 | $-13.10 | $62.42 | no | $2,302.60 | 0.3132 | no |
| `CONTROL x TP1_50` | 64 | 26 | $518.55 | $8.10 | 21.9% | $-30.70 | $-10.78 | $33.98 | no | $2,422.20 | 0.4503 | no |
| `CONTROL x TP1_75` | 64 | 26 | $1,046.70 | $16.35 | 20.3% | $-27.01 | $-8.70 | $50.69 | no | $2,721.20 | 0.3685 | no |
| `CONTROL x MFE_TRAIL` | 66 | 26 | $815.60 | $12.36 | 19.7% | $-24.56 | $-2.89 | $31.82 | no | $2,338.10 | 0.3401 | no |
| `CONTROL x ATR_STOP` | 51 | 26 | $2,915.24 | $57.16 | 35.3% | $-2.14 | $14.22 | $105.47 | yes | $3,020.20 | 0.1491 | no |
| `CONTROL x CATCAP_25` | 64 | 26 | $2,149.60 | $33.59 | 18.8% | $-14.04 | $-0.92 | $80.87 | no | $3,020.20 | 0.2126 | no |
| `CONTROL x CATCAP_30` | 64 | 26 | $1,941.95 | $30.34 | 18.8% | $-17.39 | $-3.47 | $76.68 | no | $3,020.20 | 0.2433 | no |
| `CONTROL x CATCAP_40` | 64 | 26 | $1,706.65 | $26.67 | 18.8% | $-21.19 | $-3.71 | $68.30 | no | $3,020.20 | 0.2823 | no |
| `CONTROL x CATCAP_60` | 64 | 26 | $1,304.05 | $20.38 | 18.8% | $-27.68 | $-4.53 | $54.50 | no | $3,020.20 | 0.3443 | no |
| `CONTROL x STRUCT_ONLY` | 64 | 26 | $1,327.85 | $20.75 | 18.8% | $-27.30 | $-4.53 | $55.38 | no | $3,020.20 | 0.3408 | no |
| `STRUCT8 x CONTROL` | 34 | 23 | $-877.30 | $-25.80 | 14.7% | $-38.18 | $-2.83 | $-51.65 | yes | $-191.00 | 0.8506 | no |
| `STRUCT8 x TP1_30` | 34 | 23 | $-21.15 | $-0.62 | 38.2% | $-8.04 | $-5.04 | $4.34 | no | $-70.15 | 0.5076 | no |
| `STRUCT8 x TP1_40` | 34 | 23 | $-311.80 | $-9.17 | 23.5% | $-18.38 | $-7.58 | $-10.96 | yes | $-191.00 | 0.6740 | no |
| `STRUCT8 x TP1_50` | 34 | 23 | $-938.50 | $-27.60 | 20.6% | $-36.68 | $-5.51 | $-52.45 | yes | $-191.00 | 0.9000 | no |
| `STRUCT8 x TP1_75` | 34 | 23 | $-843.95 | $-24.82 | 17.6% | $-35.10 | $-7.69 | $-44.09 | yes | $-191.00 | 0.8554 | no |
| `STRUCT8 x MFE_TRAIL` | 34 | 23 | $-832.20 | $-24.48 | 14.7% | $-37.25 | $-2.02 | $-49.74 | yes | $-191.00 | 0.8365 | no |
| `STRUCT8 x ATR_STOP` | 27 | 23 | $1,071.50 | $39.69 | 29.6% | $5.62 | $20.29 | $57.70 | yes | $925.30 | 0.2227 | no |
| `STRUCT8 x CATCAP_25` | 34 | 23 | $-284.55 | $-8.37 | 14.7% | $-20.21 | $4.30 | $-22.62 | no | $-191.00 | 0.6769 | no |
| `STRUCT8 x CATCAP_30` | 34 | 23 | $-458.40 | $-13.48 | 14.7% | $-25.48 | $-0.98 | $-27.55 | yes | $-191.00 | 0.7501 | no |
| `STRUCT8 x CATCAP_40` | 34 | 23 | $-626.10 | $-18.41 | 14.7% | $-30.56 | $-1.53 | $-37.41 | yes | $-191.00 | 0.8004 | no |
| `STRUCT8 x CATCAP_60` | 34 | 23 | $-971.10 | $-28.56 | 14.7% | $-41.02 | $-2.83 | $-57.51 | yes | $-191.00 | 0.8634 | no |
| `STRUCT8 x STRUCT_ONLY` | 34 | 23 | $-947.30 | $-27.86 | 14.7% | $-40.30 | $-2.83 | $-56.03 | yes | $-191.00 | 0.8623 | no |
| `VD1 x CONTROL` | 54 | 25 | $1,754.15 | $32.48 | 22.2% | $-20.97 | $5.49 | $68.87 | yes | $2,844.50 | 0.2606 | no |
| `VD1 x TP1_30` | 55 | 25 | $1,994.70 | $36.27 | 38.2% | $-1.74 | $-5.80 | $90.61 | no | $2,087.10 | 0.1384 | no |
| `VD1 x TP1_40` | 54 | 25 | $1,604.50 | $29.71 | 29.6% | $-11.36 | $-5.42 | $77.06 | no | $2,195.30 | 0.2265 | no |
| `VD1 x TP1_50` | 54 | 25 | $910.85 | $16.87 | 25.9% | $-26.78 | $-2.65 | $43.18 | no | $2,303.50 | 0.3679 | no |
| `VD1 x TP1_75` | 54 | 25 | $1,410.50 | $26.12 | 24.1% | $-22.38 | $-0.17 | $61.56 | no | $2,574.00 | 0.2944 | no |
| `VD1 x MFE_TRAIL` | 56 | 25 | $1,142.80 | $20.41 | 23.2% | $-19.45 | $6.76 | $37.33 | yes | $2,154.30 | 0.2738 | no |
| `VD1 x ATR_STOP` | 45 | 25 | $3,211.56 | $71.37 | 40.0% | $8.54 | $23.92 | $130.68 | yes | $2,844.50 | 0.1124 | no |
| `VD1 x CATCAP_25` | 54 | 25 | $2,484.90 | $46.02 | 22.2% | $-6.92 | $9.12 | $95.75 | yes | $2,844.50 | 0.1507 | no |
| `VD1 x CATCAP_30` | 54 | 25 | $2,277.25 | $42.17 | 22.2% | $-10.91 | $6.07 | $90.83 | yes | $2,844.50 | 0.1823 | no |
| `VD1 x CATCAP_40` | 54 | 25 | $2,041.95 | $37.81 | 22.2% | $-15.43 | $5.78 | $80.99 | yes | $2,844.50 | 0.2175 | no |
| `VD1 x CATCAP_60` | 54 | 25 | $1,639.35 | $30.36 | 22.2% | $-23.18 | $4.81 | $64.79 | yes | $2,844.50 | 0.2757 | no |
| `VD1 x STRUCT_ONLY` | 54 | 25 | $1,663.15 | $30.80 | 22.2% | $-22.72 | $4.81 | $65.83 | yes | $2,844.50 | 0.2728 | no |
| `MAX3 x CONTROL` | 41 | 26 | $-1,380.30 | $-33.67 | 14.6% | $-54.66 | $-32.26 | $-34.66 | yes | $806.00 | 0.8751 | no |
| `MAX3 x TP1_30` | 41 | 26 | $-105.45 | $-2.57 | 36.6% | $-13.49 | $-22.56 | $11.59 | no | $434.30 | 0.5531 | no |
| `MAX3 x TP1_40` | 41 | 26 | $-700.15 | $-17.08 | 24.4% | $-29.69 | $-26.52 | $-10.39 | yes | $487.40 | 0.7786 | no |
| `MAX3 x TP1_50` | 41 | 26 | $-1,521.90 | $-37.12 | 19.5% | $-51.56 | $-25.16 | $-45.59 | yes | $540.50 | 0.9334 | no |
| `MAX3 x TP1_75` | 41 | 26 | $-1,384.15 | $-33.76 | 17.1% | $-51.43 | $-32.26 | $-34.82 | yes | $673.25 | 0.8924 | no |
| `MAX3 x MFE_TRAIL` | 41 | 26 | $-1,311.80 | $-32.00 | 14.6% | $-53.87 | $-32.26 | $-31.81 | yes | $843.00 | 0.8578 | no |
| `MAX3 x ATR_STOP` | 37 | 26 | $-664.91 | $-17.97 | 27.0% | $-43.61 | $-49.94 | $6.39 | no | $806.00 | 0.6758 | no |
| `MAX3 x CATCAP_25` | 41 | 26 | $-739.55 | $-18.04 | 14.6% | $-38.64 | $-30.94 | $-8.90 | yes | $806.00 | 0.7724 | no |
| `MAX3 x CATCAP_30` | 41 | 26 | $-857.20 | $-20.91 | 14.6% | $-41.58 | $-31.20 | $-13.62 | yes | $806.00 | 0.7982 | no |
| `MAX3 x CATCAP_40` | 41 | 26 | $-1,092.50 | $-26.65 | 14.6% | $-47.46 | $-31.73 | $-23.05 | yes | $806.00 | 0.8367 | no |
| `MAX3 x CATCAP_60` | 41 | 26 | $-1,495.10 | $-36.47 | 14.6% | $-57.53 | $-33.49 | $-38.57 | yes | $806.00 | 0.8853 | no |
| `MAX3 x STRUCT_ONLY` | 41 | 26 | $-1,471.30 | $-35.89 | 14.6% | $-56.93 | $-33.49 | $-37.58 | yes | $806.00 | 0.8848 | no |

## BH-FDR survivors (q = 0.10)

**Population A: 0 survivor(s).** Nothing clears the multiple-comparison correction.

**Population B: 0 survivor(s).** Nothing clears the multiple-comparison correction.

**Survives in BOTH populations: 0** -- none. Per the prereg's second hard gate, a cell is only 'notable' if both populations agree directionally or the disagreement is itself the reported finding. With no cell clearing both, the disagreement IS the finding.

## Hard gate -- Tuesday 2026-08-04 no-harm

Tuesday was +$3,624 book-wide, the week's dominant day. Any cell that degrades it is unrecommendable regardless of aggregate expectancy.

### Population A

Control Tuesday total: **--** (n=0 trades that day).

| cell | Tue 08-04 $ | vs control | gate |
|---|--:|--:|:-:|
| _no cell had Tuesday trades_ | -- | -- | -- |

### Population B

Control Tuesday total: **$3,020.20** (n=2 trades that day).

| cell | Tue 08-04 $ | vs control | gate |
|---|--:|--:|:-:|
| `CONTROL x CONTROL` | $3,020.20 | $0.00 | PASS |
| `CONTROL x TP1_30` | $2,183.00 | $-837.20 | **DEGRADES** |
| `CONTROL x TP1_40` | $2,302.60 | $-717.60 | **DEGRADES** |
| `CONTROL x TP1_50` | $2,422.20 | $-598.00 | **DEGRADES** |
| `CONTROL x TP1_75` | $2,721.20 | $-299.00 | **DEGRADES** |
| `CONTROL x MFE_TRAIL` | $2,338.10 | $-682.10 | **DEGRADES** |
| `CONTROL x ATR_STOP` | $3,020.20 | $0.00 | PASS |
| `CONTROL x CATCAP_25` | $3,020.20 | $0.00 | PASS |
| `CONTROL x CATCAP_30` | $3,020.20 | $0.00 | PASS |
| `CONTROL x CATCAP_40` | $3,020.20 | $0.00 | PASS |
| `CONTROL x CATCAP_60` | $3,020.20 | $0.00 | PASS |
| `CONTROL x STRUCT_ONLY` | $3,020.20 | $0.00 | PASS |
| `STRUCT8 x CONTROL` | $-191.00 | $-3,211.20 | **DEGRADES** |
| `STRUCT8 x TP1_30` | $-70.15 | $-3,090.35 | **DEGRADES** |
| `STRUCT8 x TP1_40` | $-191.00 | $-3,211.20 | **DEGRADES** |
| `STRUCT8 x TP1_50` | $-191.00 | $-3,211.20 | **DEGRADES** |
| `STRUCT8 x TP1_75` | $-191.00 | $-3,211.20 | **DEGRADES** |
| `STRUCT8 x MFE_TRAIL` | $-191.00 | $-3,211.20 | **DEGRADES** |
| `STRUCT8 x ATR_STOP` | $925.30 | $-2,094.90 | **DEGRADES** |
| `STRUCT8 x CATCAP_25` | $-191.00 | $-3,211.20 | **DEGRADES** |
| `STRUCT8 x CATCAP_30` | $-191.00 | $-3,211.20 | **DEGRADES** |
| `STRUCT8 x CATCAP_40` | $-191.00 | $-3,211.20 | **DEGRADES** |
| `STRUCT8 x CATCAP_60` | $-191.00 | $-3,211.20 | **DEGRADES** |
| `STRUCT8 x STRUCT_ONLY` | $-191.00 | $-3,211.20 | **DEGRADES** |
| `VD1 x CONTROL` | $2,844.50 | $-175.70 | **DEGRADES** |
| `VD1 x TP1_30` | $2,087.10 | $-933.10 | **DEGRADES** |
| `VD1 x TP1_40` | $2,195.30 | $-824.90 | **DEGRADES** |
| `VD1 x TP1_50` | $2,303.50 | $-716.70 | **DEGRADES** |
| `VD1 x TP1_75` | $2,574.00 | $-446.20 | **DEGRADES** |
| `VD1 x MFE_TRAIL` | $2,154.30 | $-865.90 | **DEGRADES** |
| `VD1 x ATR_STOP` | $2,844.50 | $-175.70 | **DEGRADES** |
| `VD1 x CATCAP_25` | $2,844.50 | $-175.70 | **DEGRADES** |
| `VD1 x CATCAP_30` | $2,844.50 | $-175.70 | **DEGRADES** |
| `VD1 x CATCAP_40` | $2,844.50 | $-175.70 | **DEGRADES** |
| `VD1 x CATCAP_60` | $2,844.50 | $-175.70 | **DEGRADES** |
| `VD1 x STRUCT_ONLY` | $2,844.50 | $-175.70 | **DEGRADES** |
| `MAX3 x CONTROL` | $806.00 | $-2,214.20 | **DEGRADES** |
| `MAX3 x TP1_30` | $434.30 | $-2,585.90 | **DEGRADES** |
| `MAX3 x TP1_40` | $487.40 | $-2,532.80 | **DEGRADES** |
| `MAX3 x TP1_50` | $540.50 | $-2,479.70 | **DEGRADES** |
| `MAX3 x TP1_75` | $673.25 | $-2,346.95 | **DEGRADES** |
| `MAX3 x MFE_TRAIL` | $843.00 | $-2,177.20 | **DEGRADES** |
| `MAX3 x ATR_STOP` | $806.00 | $-2,214.20 | **DEGRADES** |
| `MAX3 x CATCAP_25` | $806.00 | $-2,214.20 | **DEGRADES** |
| `MAX3 x CATCAP_30` | $806.00 | $-2,214.20 | **DEGRADES** |
| `MAX3 x CATCAP_40` | $806.00 | $-2,214.20 | **DEGRADES** |
| `MAX3 x CATCAP_60` | $806.00 | $-2,214.20 | **DEGRADES** |
| `MAX3 x STRUCT_ONLY` | $806.00 | $-2,214.20 | **DEGRADES** |

## Interaction effects -- does entry x exit compound?

`interaction = actual - (control + row effect + column effect)`. A large positive value means the pair does something neither change does alone -- the whole point of crossing the matrix instead of testing entries and exits separately.

### Population A

| cell | actual exp | additive prediction | interaction | reading |
|---|--:|--:|--:|---|
| `ZONE x ATR_STOP` | $5.18 | $74.33 | $-69.15 | sub-additive (the two changes fight each other) |
| `LADDER7 x ATR_STOP` | $7.17 | $72.06 | $-64.89 | sub-additive (the two changes fight each other) |
| `LADDER8 x ATR_STOP` | $17.47 | $78.63 | $-61.16 | sub-additive (the two changes fight each other) |
| `LADDER9 x ATR_STOP` | $22.16 | $83.06 | $-60.90 | sub-additive (the two changes fight each other) |
| `ZONE x TP1_50` | $-8.39 | $-36.20 | $27.81 | super-additive (combo beats the sum of its parts) |
| `LADDER7 x TP1_50` | $-16.27 | $-38.47 | $22.20 | super-additive (combo beats the sum of its parts) |
| `ZONE x TP1_30` | $-7.70 | $-29.64 | $21.94 | super-additive (combo beats the sum of its parts) |
| `ZONE x TP1_75` | $-5.77 | $-27.22 | $21.45 | super-additive (combo beats the sum of its parts) |
| `LADDER8 x TP1_50` | $-10.84 | $-31.90 | $21.06 | super-additive (combo beats the sum of its parts) |
| `ZONE x STRUCT_ONLY` | $-1.65 | $18.69 | $-20.34 | sub-additive (the two changes fight each other) |
| `LADDER7 x STRUCT_ONLY` | $-2.75 | $16.42 | $-19.17 | sub-additive (the two changes fight each other) |
| `LADDER8 x STRUCT_ONLY` | $4.62 | $22.99 | $-18.37 | sub-additive (the two changes fight each other) |
| `LADDER7 x TP1_75` | $-11.45 | $-29.49 | $18.04 | super-additive (combo beats the sum of its parts) |
| `LADDER9 x STRUCT_ONLY` | $9.84 | $27.42 | $-17.58 | sub-additive (the two changes fight each other) |
| `LADDER7 x TP1_30` | $-14.36 | $-31.91 | $17.55 | super-additive (combo beats the sum of its parts) |
| `LADDER9 x CATCAP_25` | $5.91 | $-11.62 | $17.53 | super-additive (combo beats the sum of its parts) |
| `LADDER8 x TP1_75` | $-5.53 | $-22.92 | $17.39 | super-additive (combo beats the sum of its parts) |
| `LADDER9 x TP1_50` | $-10.88 | $-27.47 | $16.59 | super-additive (combo beats the sum of its parts) |
| `STRUCT8 x CATCAP_30` | $0.96 | $16.95 | $-15.99 | sub-additive (the two changes fight each other) |
| `LADDER7 x CATCAP_25` | $-7.04 | $-22.62 | $15.58 | super-additive (combo beats the sum of its parts) |
| _+57 further cells_ | | | | _full set in the JSON; ranked by |interaction|, none omitted from the artifact_ |

### Population B

| cell | actual exp | additive prediction | interaction | reading |
|---|--:|--:|--:|---|
| `STRUCT8 x ATR_STOP` | $39.69 | $9.19 | $30.50 | super-additive (combo beats the sum of its parts) |
| `MAX3 x TP1_30` | $-2.57 | $-31.54 | $28.97 | super-additive (combo beats the sum of its parts) |
| `STRUCT8 x TP1_30` | $-0.62 | $-23.67 | $23.05 | super-additive (combo beats the sum of its parts) |
| `STRUCT8 x TP1_40` | $-9.17 | $-29.21 | $20.04 | super-additive (combo beats the sum of its parts) |
| `MAX3 x TP1_40` | $-17.08 | $-37.08 | $20.00 | super-additive (combo beats the sum of its parts) |
| `MAX3 x ATR_STOP` | $-17.97 | $1.32 | $-19.29 | sub-additive (the two changes fight each other) |
| `STRUCT8 x TP1_50` | $-27.60 | $-39.87 | $12.27 | super-additive (combo beats the sum of its parts) |
| `MAX3 x MFE_TRAIL` | $-32.00 | $-43.48 | $11.48 | super-additive (combo beats the sum of its parts) |
| `STRUCT8 x MFE_TRAIL` | $-24.48 | $-35.61 | $11.13 | super-additive (combo beats the sum of its parts) |
| `MAX3 x TP1_50` | $-37.12 | $-47.74 | $10.62 | super-additive (combo beats the sum of its parts) |
| `STRUCT8 x TP1_75` | $-24.82 | $-31.62 | $6.80 | super-additive (combo beats the sum of its parts) |
| `STRUCT8 x CATCAP_25` | $-8.37 | $-14.38 | $6.01 | super-additive (combo beats the sum of its parts) |
| `MAX3 x TP1_75` | $-33.76 | $-39.49 | $5.73 | super-additive (combo beats the sum of its parts) |
| `MAX3 x CATCAP_30` | $-20.91 | $-25.50 | $4.59 | super-additive (combo beats the sum of its parts) |
| `MAX3 x CATCAP_25` | $-18.04 | $-22.25 | $4.21 | super-additive (combo beats the sum of its parts) |
| `STRUCT8 x CATCAP_30` | $-13.48 | $-17.63 | $4.15 | super-additive (combo beats the sum of its parts) |
| `VD1 x ATR_STOP` | $71.37 | $67.47 | $3.90 | super-additive (combo beats the sum of its parts) |
| `STRUCT8 x CATCAP_40` | $-18.41 | $-21.30 | $2.89 | super-additive (combo beats the sum of its parts) |
| `MAX3 x CATCAP_40` | $-26.65 | $-29.17 | $2.52 | super-additive (combo beats the sum of its parts) |
| `VD1 x MFE_TRAIL` | $20.41 | $22.67 | $-2.26 | sub-additive (the two changes fight each other) |
| _+13 further cells_ | | | | _full set in the JSON; ranked by |interaction|, none omitted from the artifact_ |

## /fable-too-good audit of the winning cell -- READ THIS BEFORE THE TABLE ABOVE

`ATR_STOP` won every non-ladder row in both populations by a wide margin. That shape demands an artifact hunt before it is reported as an edge. The hunt found two real structural problems, and decomposing them inverts the headline.

**Problem 1 -- look-ahead.** `_atr_stop_col` derives the stop width from `opt_df[:6]`, and `_opt_bars_from` returns bars with `ts >= entry`. So the stop is computed from the realized high/low of the first 6 bars AFTER entry, then tested against those same bars. A trade that whipsaws right after entry gets a large ATR, hence a wide stop, hence is NOT stopped on the whipsaw; a quiet trade gets a tight one. The rule hands the widest stops to exactly the trades that would otherwise have been stopped out (C6).

**Problem 2 -- mode confound.** Control is `stop_mode="structure"` (`structure_stop_enabled=True`). `_atr_stop_col` returns `stop_mode="premium"`, which turns structure stops OFF. The column changes two things at once.

**Checked and NOT a confound:** the column drops `profit_lock_arm_scope`, but `exit_manager` defaults it to `post_tp1` -- the same value control carries. Recorded so nobody re-hunts it.

**Walker parity -- the biggest suspicion, and it is CLEARED.** `ATR_STOP` was the only population-A column walked by `walk_lane_dynamic_shape`, a hand-duplicated twin of `sl.walk_lane`; a cross-engine comparison is the SIM-EXIT-SHAPE-PARITY scar. Running the control shape through the twin reproduces `sl.walk_lane` **exactly**: $16.06/trade on n=289 versus $16.06 on n=289, delta **$0.00**. The twin is faithful; the walker is not the explanation.

| column | n | exp $/tr | total $ | WR | drop-best exp | 1st half | 2nd half | stable | boot p |
|---|--:|--:|--:|--:|--:|--:|--:|:-:|--:|
| `TWIN_CONTROL` | 289 | $16.06 | $4,641.00 | 24.6% | $8.43 | $14.39 | $17.81 | yes | 0.3515 |
| `ATR_LOOKAHEAD` | 270 | $95.26 | $25,720.34 | 34.8% | $84.98 | $54.91 | $138.08 | yes | 0.0284 |
| `ATR_CLEAN` | 270 | $69.67 | $18,811.04 | 33.3% | $59.29 | $34.36 | $106.04 | yes | 0.0748 |
| `PREM_STATIC_20` | 291 | $76.61 | $22,294.40 | 21.0% | $67.01 | $60.76 | $93.02 | yes | 0.0153 |

### The decomposition -- where the $79.20 actually comes from

| component | $/trade | what it is |
|---|--:|---|
| stop_mode: structure -> premium | **$60.55** | turning the structure stop OFF and using a flat -20% premium stop |
| look-ahead artifact | $25.59 | pure hindsight, not available live |
| the dynamic width itself | **$-6.94** | ATR-computed width vs a flat -20%, measured with the look-ahead removed |
| **total** | **$79.20** | reconciles to the $95.26 - $16.06 headline gap |

**So the dynamic stop is not the edge.** Measured honestly, a per-trade ATR-computed stop width is *slightly worse* than a flat -20% premium stop. Roughly a third of the headline was hindsight. What is left -- and it is the large majority of it -- is a single binary flag: **the structure stop.**

This is a POST-HOC finding. The frozen prereg tested `ATR_STOP`; it did not pre-register `stop_mode`. It therefore does NOT ship on this evidence -- it gets its own frozen pre-registration and its own run, on both populations, with the Tuesday gate evaluable. Shipping a post-hoc cell is how the bar gets softened.

**Open caveats on the stop_mode result, stated rather than buried:**
- The Tuesday 2026-08-04 hard gate is **untestable** on this cohort -- the CONTROL entry row admitted zero trades on that date (`tuesday_0804_n=0`). Not passed; not evaluable.
- It contradicts explicitly ratified doctrine (chart-stop-primary, 2026-06-18). That does not make it wrong -- ribbon flip being a lagging exit is already C28 in the lessons index, and this is consistent with it -- but reversing a ratified mechanism needs its own evidence, not a side effect of an exit-grid cell.
- Population B (real broker fills) has not been decomposed the same way. Its `ATR_STOP` cell carries the identical look-ahead and mode confound, so its $57-71/tr is NOT independent corroboration of the mode effect yet.
- Win rate goes DOWN under the premium stop (21.0% vs 24.6%) while total P&L goes up: fewer winners, but losers cut faster and winners not flipped out early. That is a coherent mechanism, not just a number -- but it is the mechanism that needs confirming, not the dollar figure.
- This is a replay population, not the live book. The replayed as-shipped control earns $16.06/trade here; the live book's last 23-day base rate ex-Tuesday is negative. Treat the delta as a signal to test, never as a promised dollar amount.

## Method disclosures

- **Sequential, one-position-at-a-time (NOT_FLAT) walk**, re-derived independently per (row, col) cell -- a wider stop's suppression of later re-entries is measured per cell, never assumed or recombined across independently-simulated trades.
- **Exit engine identical across both populations**: `exit_manager_walk.walk_exit_manager` -> `exit_manager.plan_exit_actions`, never `simulator_real` (the 2026-07-09 SIM-EXIT-SHAPE-PARITY scar stays closed).
- **5-minute OPRA touch-resolution** for both populations, held constant so resolution is never itself a confound.
- **Runner-cohort is incomplete by construction for most Population-A columns.** The reused `score_ladder_replay` trade schema does not tag TP1 fills, so `runner_cohort_n` is only populated for `ATR_STOP` (this file's own walker) and for Population B. Elsewhere `runner_cohort_n=0` means NOT MEASURED, never 'zero trades reached TP1'. Every other battery component is computed for all cells.
- **`MFE_TRAIL` and `ATR_STOP` are deliberately simpler than a from-scratch dynamic exit** (disclosed in the prereg). The authoritative per-trade dynamic-exit study is the sibling [`DYNAMIC-EXITS-2026-08-09.md`](DYNAMIC-EXITS-2026-08-09.md); where the two disagree, trust the sibling for the exit-only question.

Raw per-cell JSON: `ENTRY-EXIT-MATRIX-2026-08-09.json` (committed). Per-trade detail: `ENTRY-EXIT-MATRIX-2026-08-09-trades.json` -- 35MB, **gitignored and local-only**, regenerable by re-running the harness. Artifact audit: `ENTRY-EXIT-MATRIX-ATR-AUDIT-2026-08-09.json`.

