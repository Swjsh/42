# AI-ROBOTICS SUPPLY CHAIN — minerals → components → robots (living doc)

> **Provenance.** J directive 2026-09-08 14:00 ET (mid-session): *"we need to be looking at AI Robotic stocks and trading them. look at Acuity also, look at mining companies that AI robots use. map out the entire thing from minerals all the way to products and figure out what companies we should be watching and trading."* Built the same afternoon: three Sonnet research fires (upstream / midstream / downstream, web-verified, every row sourced) + a **live options-liquidity screen at 14:14–14:19 ET** over 137 US-listed names through the multi/tickers lane's own gate (`backtest/tools/weekly_universe_screen.py`, 8% spread, mid ≥ $0.20, $1,500 3-lot cap, indicative feed). Living doc — **append, never fork** (OP-22). Screens: [`universe-screen-robotics-upstream-2026-09-08.json`](../../analysis/multi-lane/universe-screen-robotics-upstream-2026-09-08.json) · [`…-mid-…`](../../analysis/multi-lane/universe-screen-robotics-mid-2026-09-08.json) · [`…-down-…`](../../analysis/multi-lane/universe-screen-robotics-down-2026-09-08.json) · universe: [`robotics-chain-universe-2026-09-08.json`](../../analysis/multi-lane/robotics-chain-universe-2026-09-08.json). Alpaca watchlist **`AI-Robotics-Chain`** (safe-2, 43 names) created 2026-09-08 18:20Z.

## 0. Verdict

- **The chain is real and mapped: ~150 names across 3 layers, 14 nodes.** The names with *named, dollar-quantified* humanoid contracts are mostly **not US-tradeable** (Tuopu, Sanhua, LG Energy Solution, Foxconn, Harmonic Drive, Nabtesco, Hiwin, Unitree, UBTech). The one US exception with a named humanoid manufacturing contract is **JBL** (Apptronik Apollo); the one US mine-to-magnet vertical is **MP**.
- **"Trading them" hits the same wall as WEEKLY-OPTIONS §2b: hot ≠ tradeable.** At the lane's 8% gate, **13 of 122 screenable names** are tier-1 today — and 9 of those are the mega-caps the tickers lane *already* trades (NVDA AVGO QCOM AMZN PLTR TSLA INTC MSFT GOOGL). The new tier-1 names are **ONDS (5.7%), BHP (5.5%), SIL (8.0%), AME (2.4%)**. Every pure robotics or minerals name fails on spread: MP 17%, SYM 21%, TER 27%, ISRG 17%, OUST 17%, SERV 26%, HUMN 41%, REMX 88%.
- **Express the theme through its liquid vehicle.** For options, that is the mega-cap compute/robot-owner layer (NVDA/TSLA/AMZN/GOOGL), which the desk is already positioned to trade. The pure-plays are **watch-on-headline** names: the tape will move them, the chains will not fill at our size.
- **Acuity (AYI) is not a robotics stock.** Smart-building software (Distech/Atrius/QSC) with real earnings momentum (+17.5% on its last print, next ~9/30). Watch it as its own AI-adjacent earnings name; ATM spread 39% today.
- **The whole upstream layer has two hard dates: 11/10 (China rare-earth control suspension expires) and 11/27 (Ga/Ge/Sb).** Downstream: **10/28 TSLA Q3 (Optimus)**, **11/23 SYM**, **11/30–12/3 GTC DC**, Agility SPAC close (CCXI→AGLT).

## 1. The chain — one screen

```
MINERALS ───────────────► COMPONENTS ─────────────────► ROBOTS / DEPLOYERS ──────► BASKETS
NdPr/Dy/Tb magnets        Actuators/reducers/motors     Humanoid  TSLA XPEV (AGLT)   HUMN KOID WDRN
  MP USAR UUUU            TKR RRX MOG.A | Tuopu Sanhua    9880.HK Unitree Rainbow    BOTZ ROBO ROBT
  LYSCF NEO ILU CRML      HDS Nabtesco Hiwin Nidec       Proxies  NVDA MSFT AMZN     ARTY ARKQ
Copper                    Sensors                        Industrial SYM TER ROK       REMX LIT COPX
  FCX SCCO TECK BHP RIO     OUST AEVA HSAI NOVT VPG        CGNX ZBRA | ABB Fanuc       SIL PPLT
  IVN TMQ                   CGNX ON STM SONY               Yaskawa Keyence Omron
Lithium/Ni/Co/Mn/C        Compute/memory/foundry         Service  SERV RR KSCP GXO
  ALB SQM LAC SGML VALE     NVDA QCOM NXPI ADI TXN ARM     Surgical ISRG PRCT MDT SYK JNJ
  GLNCY NVX                 MU TSM AMAT LRCX KLAC ASML     Autonomy GOOGL AUR PONY WRD
Tungsten/Sb/Ti/Ga/Ge        AMKR APH TEL | Infineon        BIDU UBER LYFT KDK MBLY
  ALM UAMY PPTA IPX VNP   Batteries                       Drones   AVAV KTOS RCAT ONDS
Silver/PGM/helium           ENVX AMPX | LGES CATL Pana     DPRO UMAC | PLTR (adj.)
  HL PAAS AG SBSW ASPI    EMS/structure  JBL | Foxconn    Not robotics: AYI
                          Software  NVDA GOOGL PTC SNPS
```
Bold-face in the layer tables below marks US-listed with a real options chain. Pipe `|` separates non-US-tradeable names that are nonetheless the actual suppliers.

## 2. What is TRADEABLE today — the live screen (2026-09-08 14:14–14:19 ET, RTH)

Gate = `automation/state/multi/params.json` liquidity_gate: ≤8% spread on the ATM call at the nearest listed expiry ≥0 DTE, mid ≥ $0.20, 3 contracts ≤ $1,500. **Indicative feed** (no OPRA on these keys) — spreads are a *ranking* signal, re-verify before any order. Names with only monthly chains were measured at the 9/18 expiry (10 DTE); names with dailies/weeklies at 9/9–9/11.

| Sym | Layer | Spot | Exp (DTE) | ATM mid | Spread % | 3-lot $ | Tier |
|---|---|---|---|---|---|---|---|
| **AMZN** | L3 robots/autonomy | 256.95 | 2026-09-09 (1) | 1.42 | 0.7 | 424 | TIER1_tradeable |
| **PLTR** | L3 robots/autonomy | 171.56 | 2026-09-11 (3) | 3.13 | 1.3 | 939 | TIER1_tradeable |
| **TSLA** | L3 robots/autonomy | 366.14 | 2026-09-09 (1) | 4.28 | 1.6 | 1282 | TIER1_tradeable |
| **INTC** | L3 robots/autonomy | 105.16 | 2026-09-09 (1) | 1.75 | 1.7 | 524 | TIER1_tradeable |
| **MSFT** | L3 robots/autonomy | 491.77 | 2026-09-09 (1) | 2.50 | 2.0 | 748 | TIER1_tradeable |
| **AME** | L2 components | 239.40 | 2026-09-18 (10) | 3.81 | 2.4 | 1142 | TIER1_tradeable |
| **NVDA** | L2 components | 225.97 | 2026-09-09 (1) | 2.29 | 3.1 | 686 | TIER1_tradeable |
| **AVGO** | L2 components | 368.90 | 2026-09-09 (1) | 2.98 | 3.4 | 894 | TIER1_tradeable |
| **GOOGL** | L3 robots/autonomy | 338.05 | 2026-09-09 (1) | 2.50 | 3.6 | 748 | TIER1_tradeable |
| **QCOM** | L2 components | 175.44 | 2026-09-11 (3) | 4.09 | 5.4 | 1227 | TIER1_tradeable |
| **BHP** | L1 minerals | 92.34 | 2026-09-18 (10) | 2.18 | 5.5 | 654 | TIER1_tradeable |
| **ONDS** | L3 robots/autonomy | 7.70 | 2026-09-11 (3) | 0.35 | 5.7 | 105 | TIER1_tradeable |
| **SIL** | L1 minerals | 99.04 | 2026-09-18 (10) | 3.77 | 8.0 | 1131 | TIER1_tradeable |
| **AUR** | L3 robots/autonomy | 6.49 | 2026-09-11 (3) | 0.12 | 8.0 | 38 | MID<$0.20 |
| **MU** | L2 components | 1020.78 | 2026-09-09 (1) | 14.31 | 1.5 | 4293 | TIER2_too_expensive_for_3_lots |
| **MRVL** | L2 components | 228.74 | 2026-09-11 (3) | 7.00 | 2.9 | 2100 | TIER2_too_expensive_for_3_lots |
| **TSM** | L2 components | 440.81 | 2026-09-11 (3) | 6.77 | 3.5 | 2031 | TIER2_too_expensive_for_3_lots |
| **ARM** | L2 components | 262.83 | 2026-09-11 (3) | 8.12 | 7.5 | 2438 | TIER2_too_expensive_for_3_lots |
| **WMT** | L3 robots/autonomy | 106.03 | 2026-09-11 (3) | 1.06 | 8.4 | 320 | TIER2_spread_discipline |
| **LRCX** | L2 components | 319.55 | 2026-09-11 (3) | 7.53 | 8.6 | 2258 | TIER2_spread_discipline |
| **VALE** | L1 minerals | 15.64 | 2026-09-11 (3) | 0.34 | 8.7 | 104 | TIER2_spread_discipline |
| **UBER** | L3 robots/autonomy | 73.42 | 2026-09-11 (3) | 1.38 | 8.7 | 414 | TIER2_spread_discipline |
| **BIDU** | L3 robots/autonomy | 91.97 | 2026-09-11 (3) | 1.70 | 9.4 | 510 | TIER2_spread_discipline |
| **APH** | L2 components | 82.94 | 2026-09-18 (10) | 2.65 | 9.4 | 794 | TIER2_spread_discipline |
| **SYK** | L3 robots/autonomy | 279.81 | 2026-09-18 (10) | 6.46 | 11.6 | 1940 | TIER2_spread_discipline |
| **TXN** | L2 components | 257.60 | 2026-09-11 (3) | 3.97 | 12.1 | 1191 | TIER2_spread_discipline |
| **LYFT** | L3 robots/autonomy | 16.10 | 2026-09-11 (3) | 0.33 | 12.1 | 99 | TIER2_spread_discipline |
| **ST** | L2 components | 42.82 | 2026-09-18 (10) | 1.30 | 12.3 | 390 | TIER2_spread_discipline |
| **KLAC** | L2 components | 188.35 | 2026-09-11 (3) | 4.88 | 12.5 | 1462 | TIER2_spread_discipline |
| **MCHP** | L2 components | 73.81 | 2026-09-11 (3) | 1.47 | 13.6 | 441 | TIER2_spread_discipline |
| **FLEX** | L2 components | 114.66 | 2026-09-18 (10) | 4.66 | 13.7 | 1398 | TIER2_spread_discipline |
| **FCX** | L1 minerals | 76.88 | 2026-09-11 (3) | 1.57 | 14.0 | 471 | TIER2_spread_discipline |
| **ENVX** | L2 components | 3.50 | 2026-09-11 (3) | 0.14 | 14.3 | 42 | TIER2_spread_discipline |
| **TKR** | L2 components | 124.10 | 2026-09-18 (10) | 2.87 | 14.3 | 860 | TIER2_spread_discipline |
| **JNJ** | L3 robots/autonomy | 270.62 | 2026-09-11 (3) | 3.08 | 14.6 | 926 | TIER2_spread_discipline |
| **UUUU** | L1 minerals | 14.93 | 2026-09-11 (3) | 0.41 | 14.6 | 123 | TIER2_spread_discipline |
| **AVAV** | L3 robots/autonomy | 149.37 | 2026-09-11 (3) | 9.10 | 14.7 | 2730 | TIER2_spread_discipline |
| **AG** | L1 minerals | 21.00 | 2026-09-11 (3) | 0.54 | 14.8 | 162 | TIER2_spread_discipline |
| **AMKR** | L2 components | 51.30 | 2026-09-11 (3) | 1.60 | 15.0 | 480 | TIER2_spread_discipline |
| **SCCO** | L1 minerals | 209.83 | 2026-09-11 (3) | 4.33 | 15.9 | 1298 | TIER2_spread_discipline |
| **OUST** | L2 components | 37.74 | 2026-09-11 (3) | 1.50 | 16.7 | 448 | TIER2_spread_discipline |
| **SANM** | L2 components | 207.44 | 2026-09-18 (10) | 8.23 | 16.8 | 2469 | TIER2_spread_discipline |
| **MP** | L1 minerals | 55.90 | 2026-09-11 (3) | 1.56 | 17.2 | 470 | TIER2_spread_discipline |
| **ISRG** | L3 robots/autonomy | 353.10 | 2026-09-11 (3) | 6.59 | 17.3 | 1977 | TIER2_spread_discipline |
| **NXPI** | L2 components | 224.99 | 2026-09-18 (10) | 9.40 | 17.8 | 2822 | TIER2_spread_discipline |
| **PPTA** | L1 minerals | 25.08 | 2026-09-18 (10) | 1.18 | 17.9 | 352 | TIER2_spread_discipline |
| **JBL** | L2 components | 311.59 | 2026-09-11 (3) | 5.95 | 18.1 | 1785 | TIER2_spread_discipline |
| **TECK** | L1 minerals | 72.17 | 2026-09-11 (3) | 1.40 | 18.6 | 420 | TIER2_spread_discipline |
| **KTOS** | L3 robots/autonomy | 48.74 | 2026-09-11 (3) | 1.34 | 18.6 | 404 | TIER2_spread_discipline |
| **ALM** | L1 minerals | 19.34 | 2026-09-18 (10) | 0.85 | 18.8 | 255 | TIER2_spread_discipline |
| **TMQ** | L1 minerals | 3.54 | 2026-09-18 (10) | 0.57 | 19.1 | 172 | TIER2_spread_discipline |
| **AMAT** | L2 components | 470.77 | 2026-09-11 (3) | 10.97 | 19.2 | 3292 | TIER2_spread_discipline |
| **STM** | L2 components | 52.33 | 2026-09-11 (3) | 1.35 | 19.3 | 405 | TIER2_spread_discipline |
| **COPX** | L1 minerals | 95.07 | 2026-09-11 (3) | 1.86 | 19.4 | 558 | TIER2_spread_discipline |
| **ASML** | L2 components | 1769.54 | 2026-09-11 (3) | 33.88 | 19.8 | 10162 | TIER2_spread_discipline |
| **RIO** | L1 minerals | 104.31 | 2026-09-18 (10) | 1.75 | 19.9 | 526 | TIER2_spread_discipline |
| **ON** | L2 components | 72.27 | 2026-09-11 (3) | 1.60 | 20.0 | 480 | TIER2_spread_discipline |
| **CRML** | L1 minerals | 7.28 | 2026-09-11 (3) | 0.24 | 20.4 | 74 | TIER2_spread_discipline |
| **RRX** | L2 components | 165.46 | 2026-09-18 (10) | 5.61 | 20.7 | 1683 | TIER2_spread_discipline |
| **HL** | L1 minerals | 20.63 | 2026-09-11 (3) | 0.62 | 20.8 | 188 | TIER2_spread_discipline |
| **SYM** | L2 components | 43.72 | 2026-09-11 (3) | 1.15 | 20.9 | 345 | TIER2_spread_discipline |
| **UMAC** | L3 robots/autonomy | 25.62 | 2026-09-11 (3) | 1.15 | 20.9 | 345 | TIER2_spread_discipline |
| **CCXI** | L3 robots/autonomy | 14.11 | 2026-09-18 (10) | 0.47 | 21.3 | 141 | TIER2_spread_discipline |
| **ALB** | L1 minerals | 128.56 | 2026-09-11 (3) | 2.22 | 21.6 | 666 | TIER2_spread_discipline |
| **MDT** | L3 robots/autonomy | 92.86 | 2026-09-11 (3) | 1.01 | 21.8 | 303 | TIER2_spread_discipline |
| **XMTR** | L2 components | 94.84 | 2026-09-18 (10) | 4.17 | 21.8 | 1252 | TIER2_spread_discipline |
| **ROK** | L2 components | 430.60 | 2026-09-18 (10) | 9.07 | 22.1 | 2721 | TIER2_spread_discipline |
| **ADI** | L2 components | 362.43 | 2026-09-11 (3) | 5.20 | 22.3 | 1560 | TIER2_spread_discipline |
| **TM** | L3 robots/autonomy | 192.03 | 2026-09-18 (10) | 4.46 | 22.7 | 1336 | TIER2_spread_discipline |
| **CLS** | L2 components | 335.28 | 2026-09-11 (3) | 9.57 | 23.1 | 2872 | TIER2_spread_discipline |
| **BOTZ** | L3 robots/autonomy | 35.73 | 2026-09-18 (10) | 0.43 | 23.3 | 129 | TIER2_spread_discipline |
| **ZBRA** | L3 robots/autonomy | 348.82 | 2026-09-18 (10) | 8.25 | 23.5 | 2475 | TIER2_spread_discipline |
| **TEL** | L2 components | 206.58 | 2026-09-18 (10) | 3.36 | 23.8 | 1008 | TIER2_spread_discipline |
| **EMR** | L2 components | 152.04 | 2026-09-11 (3) | 1.62 | 24.7 | 486 | AVOID |
| **UAMY** | L1 minerals | 5.49 | 2026-09-11 (3) | 0.20 | 25.6 | 58 | AVOID |
| **DPRO** | L3 robots/autonomy | 5.92 | 2026-09-18 (10) | 0.42 | 25.9 | 128 | AVOID |
| **LAC** | L1 minerals | 3.03 | 2026-09-11 (3) | 0.12 | 26.1 | 34 | AVOID |
| **MBLY** | L3 robots/autonomy | 8.57 | 2026-09-11 (3) | 0.23 | 26.1 | 69 | AVOID |
| **SERV** | L3 robots/autonomy | 4.87 | 2026-09-11 (3) | 0.12 | 26.1 | 34 | AVOID |
| **USAR** | L1 minerals | 17.95 | 2026-09-11 (3) | 0.61 | 26.2 | 183 | AVOID |
| **TER** | L2 components | 373.44 | 2026-09-11 (3) | 11.25 | 26.8 | 3375 | AVOID |
| **PAAS** | L1 minerals | 51.41 | 2026-09-11 (3) | 1.52 | 26.9 | 458 | AVOID |
| **PTC** | L2 components | 133.58 | 2026-09-18 (10) | 4.08 | 27.4 | 1224 | AVOID |
| **METC** | L1 minerals | 12.58 | 2026-09-18 (10) | 0.55 | 27.5 | 164 | AVOID |
| **SBSW** | L1 minerals | 13.00 | 2026-09-18 (10) | 0.50 | 28.0 | 150 | AVOID |
| **SLDP** | L2 components | 2.60 | 2026-09-18 (10) | 0.15 | 32.3 | 46 | AVOID |
| **QS** | L2 components | 5.68 | 2026-09-11 (3) | 0.28 | 32.7 | 82 | AVOID |
| **GXO** | L3 robots/autonomy | 46.75 | 2026-09-18 (10) | 0.88 | 33.1 | 262 | AVOID |
| **SQM** | L1 minerals | 75.83 | 2026-09-18 (10) | 2.71 | 35.1 | 812 | AVOID |
| **TDY** | L2 components | 607.50 | 2026-09-18 (10) | 9.95 | 35.9 | 2984 | AVOID |
| **ASPI** | L1 minerals | 4.21 | 2026-09-11 (3) | 0.27 | 37.0 | 81 | AVOID |
| **RCAT** | L3 robots/autonomy | 8.74 | 2026-09-11 (3) | 0.49 | 38.4 | 148 | AVOID |
| **AYI** | L3 robots/autonomy | 327.69 | 2026-09-18 (10) | 6.00 | 38.9 | 1798 | AVOID |
| **HUMN** | L3 robots/autonomy | 30.35 | 2026-09-18 (10) | 0.97 | 41.2 | 291 | AVOID |
| **AMPX** | L2 components | 10.46 | 2026-09-11 (3) | 0.30 | 46.7 | 90 | AVOID |
| **NOVT** | L2 components | 151.13 | 2026-09-18 (10) | 6.03 | 46.8 | 1809 | AVOID |
| **XPEV** | L3 robots/autonomy | 10.96 | 2026-09-11 (3) | 0.17 | 47.1 | 51 | AVOID |
| **SLI** | L1 minerals | 2.42 | 2026-09-18 (10) | 0.10 | 47.6 | 32 | AVOID |
| **VPG** | L2 components | 65.55 | 2026-09-18 (10) | 3.34 | 49.1 | 1002 | AVOID |
| **SNPS** | L2 components | 396.54 | 2026-09-11 (3) | 8.52 | 50.0 | 2556 | AVOID |
| **PDYN** | L3 robots/autonomy | 5.79 | 2026-09-18 (10) | 0.25 | 56.0 | 75 | AVOID |
| **SONY** | L2 components | 23.55 | 2026-09-11 (3) | 0.33 | 58.5 | 98 | AVOID |
| **SGML** | L1 minerals | 10.38 | 2026-09-18 (10) | 0.68 | 58.8 | 204 | AVOID |
| **KDK** | L3 robots/autonomy | 3.94 | 2026-09-18 (10) | 0.17 | 62.9 | 52 | AVOID |
| **PRLB** | L2 components | 81.92 | 2026-09-18 (10) | 3.50 | 63.6 | 1052 | AVOID |
| **RR** | L3 robots/autonomy | 1.76 | 2026-09-11 (3) | 0.01 | 66.7 | 4 | AVOID |
| **PONY** | L3 robots/autonomy | 7.30 | 2026-09-11 (3) | 0.12 | 66.7 | 36 | AVOID |
| **IPX** | L1 minerals | 22.61 | 2026-09-18 (10) | 1.18 | 67.2 | 352 | AVOID |
| **DQ** | L1 minerals | 12.63 | 2026-09-18 (10) | 0.35 | 68.6 | 105 | AVOID |
| **ARTY** | L3 robots/autonomy | 77.06 | 2026-09-18 (10) | 2.35 | 70.4 | 704 | AVOID |
| **HXL** | L2 components | 91.83 | 2026-09-18 (10) | 2.83 | 78.2 | 848 | AVOID |
| **GSM** | L1 minerals | 4.63 | 2026-09-18 (10) | 0.76 | 86.1 | 226 | AVOID |
| **REMX** | L1 minerals | 76.96 | 2026-09-18 (10) | 2.62 | 88.0 | 788 | AVOID |
| **ARKQ** | L3 robots/autonomy | 124.62 | 2026-09-18 (10) | 2.02 | 88.4 | 608 | AVOID |
| **NB** | L1 minerals | 4.18 | 2026-09-11 (3) | 0.33 | 89.2 | 98 | AVOID |
| **PPLT** | L1 minerals | 16.70 | 2026-09-18 (10) | 0.45 | 101.1 | 134 | AVOID |
| **MBOT** | L3 robots/autonomy | 1.50 | 2026-09-18 (10) | 0.49 | 131.3 | 148 | AVOID |
| **ROBT** | L3 robots/autonomy | 58.07 | 2026-09-18 (10) | 0.88 | 149.7 | 262 | AVOID |
| **ICOP** | L1 minerals | 59.35 | 2026-09-18 (10) | 1.95 | 150.8 | 585 | AVOID |
| **LIT** | L1 minerals | 73.94 | 2026-09-18 (10) | 1.55 | 189.7 | 465 | AVOID |
| **ROBO** | L3 robots/autonomy | 80.00 | 2026-09-18 (10) | 1.68 | 190.5 | 504 | AVOID |
| **PICK** | L1 minerals | 66.55 | 2026-09-18 (10) | 1.46 | 195.9 | 438 | AVOID |

Unscreenable (no ATM two-sided quote or no expiry in window): PLL (no listed expiry in the min-DTE window), GLNCY (no spot price), AEVA (no ATM-band snapshots returned), HSAI (no ATM-band snapshots returned), CGNX (no ATM-band snapshots returned), VLD (no listed expiry in the min-DTE window), HMC (no ATM-band snapshots returned), KSCP (no listed expiry in the min-DTE window), KITT (no listed expiry in the min-DTE window), PRCT (no ATM-band snapshots returned), STXS (no ATM-band snapshots returned), RBOT (no listed expiry in the min-DTE window), WRD (no ATM-band snapshots returned), KOID (no two-sided quotes in the ATM band), WDRN (no listed expiry in the min-DTE window)

**Reading it:**
- **Tier 1 that is NEW to the desk:** ONDS (drones, 30M sh/day retail flow, +217% — extended), BHP (copper/nickel major, 10-DTE monthly), SIL (silver miners ETF, exactly at the gate), AME (diversified instruments — not a robotics story). AUR passed on spread but its $0.12 ATM mid is below the $0.20 floor.
- **Tight but priced out at 3 lots:** MU (1.5%), MRVL (2.9%), TSM (3.5%), ARM (7.5%) — liquid, but a 3-lot ATM runs $2,000–4,300 against a $1,500 cap. Tradeable in a wider-cap account or at 1–2 lots (which the doctrine forbids for the runner structure).
- **Spread-discipline band (8–25%)** holds the *actual* robotics chain: APH 9.4, TKR 14.3, OUST 16.7, JBL 18.1, ISRG 17.3, MP 17.2, KTOS 18.6, SYM 20.9, RRX 20.7, TEL 23.8, AVAV 14.7, FCX 14.0, UUUU 14.6, SCCO 15.9. These are the names that will *move* on robotics headlines and *cost* 15–25% of premium to enter and exit.
- **Avoid band (>25%)** is where the retail-momentum names live: SERV 26, MBLY 26, USAR 26, TER 27, RCAT 38, AYI 39, HUMN 41, XPEV 47, RR 67, PONY 67 — plus every thematic ETF except BOTZ (23%). The ETFs are equity vehicles, not options vehicles, at our size.

## 3. Watch tiers — who we watch, and how

| Tier | Names | How it is expressed | Status |
|---|---|---|---|
| **A · trade now, existing lanes** | NVDA TSLA AMZN (tickers-1/2 already), GOOGL MSFT PLTR INTC AVGO QCOM | 0DTE/1DTE via the armed tickers lane's production scorer — **no build needed, no universe change** (the tickers arms are pre-registered and mid-window) | ✅ live |
| **B · robotics pure-plays, watch on headline** | MP UUUU USAR FCX SCCO · SYM TER ISRG CGNX · APH TEL TKR RRX JBL · OUST AEVA · AVAV KTOS ONDS · SERV · XPEV MBLY | Alpaca watchlist `AI-Robotics-Chain`; scanners (movers / most-actives / news / gap) already read the whole optionable market, so a catalyst-day spread collapse (the MRNA 08-19 pattern) will surface without a code change | ✅ watchlist |
| **C · theme baskets** | HUMN KOID BOTZ (WDRN, ROBO, ROBT, ARTY, ARKQ) | Equity vehicles only; options unfit (23–190% spreads). Useful as *sentiment gauges* for the humanoid trade, not as trades | 👁 gauge |
| **D · the real suppliers, not US-tradeable** | Tuopu, Sanhua, Zhaowei, Green Harmonic (no ticker), Harmonic Drive, Nabtesco, Hiwin, Nidec, LG Energy Solution, CATL, Panasonic, Keyence, Fanuc, Yaskawa, Foxconn, Unitree, UBTech, Rainbow, Lynas, Iluka, China Northern REE | Read-through only: their prints and orders are the *evidence* for the US names' theses (e.g. a Tuopu/Sanhua order = Optimus is real; Lynas/China Northern = the 11/10 tape) | 📖 read |
| **E · not a robotics stock** | AYI | Own list; earnings ~9/30; AIS segment +14.9% is the number that matters | 👁 separate |

## 4. Acuity — the answer

See §3.0 in the downstream layer for the verified facts. Short form: **Acuity Inc (AYI)**, $9.7B, is a building-intelligence company (Distech BMS + Atrius data + QSC AV) with an "AI maximalist" management. Its growth segment is real (AIS $303.5M, +14.9%, 25.1% margin) and the stock rewarded the last beat with +17.5%. It will not react to Optimus/Waymo headlines; management even called data-center construction a *headwind* to its lighting segment. Watch it for the ~9/30 print, not as a robotics expression. Two private "Acuity" robotics startups exist (Leeds UK inspection robots; a robot training-data vendor); neither has a ticker.

## 5. Catalyst calendar — next 90 days (dated)

| Date (2026) | Event | Layer | Names |
|---|---|---|---|
| Sept (ongoing) | Foxconn Vietnam humanoid trial production (official Nov) | L2 | Foxconn (2317.TW), read-through NVDA |
| Sept | ASP Isotopes first liquid-helium shipment | L1 | ASPI |
| ~9/30–10/1 | Acuity FQ4 earnings (pre-mkt) | — | AYI |
| 10/16 | China Northern Rare Earth earnings — quota/pricing read before 11/10 | L1 | 600111.SS → MP USAR UUUU |
| mid-Oct | TSM Q3 | L2 | TSM, semicap |
| ~10/21–28 | Q3 earnings cluster (TKR, MOG, CGNX, TDY, AME, TXN, ASML, APH) | L2 | — |
| **10/28 after close** | **Tesla Q3 — Optimus production number or slip; robotaxi city count** | L3 | TSLA, HUMN/KOID, Tuopu/Sanhua/LGES read-through |
| ~10/29 | MP Materials Q3; first commercial GM magnet shipments guided Q4 | L1 | MP |
| **11/10** | **China rare-earth export-control suspension expires** (Oct-2025 framework snaps back unless extended) | L1 | MP USAR UUUU LYSCF REMX; every actuator name |
| 11/23 | Symbotic FQ4 — Walmart 400-system pipeline | L3 | SYM |
| **11/27** | **China gallium/germanium/antimony export-ban suspension expires** | L1 | VNP UAMY PPTA |
| 11/30–12/3 | NVIDIA GTC Washington DC — physical-AI/robotics track | L2 | NVDA + named adopters |
| by 12/31 | XPeng IRON mass production start (line commissioned 9/8) | L3 | XPEV |
| 2H26, no date | Agility Robotics SPAC close (CCXI → AGLT) — first US pure-play humanoid listing | L3 | CCXI/AGLT, HUMN, KOID |
| Jan 2027 | Section 232 refined-copper exemption review; CES 2027 (Jan 6–9) | L1/L3 | FCX SCCO; humanoid demos |

## 6. Dead, delisted, mislabelled — never re-list

| Name | Why |
|---|---|
| IRBT (iRobot) | Chapter 11 12/14/25; equity to Picea Robotics; $5M OTC shell |
| BGRY (Berkshire Grey) | Private (SoftBank) since 2023 |
| AMBA (Ambarella) | Acquired by NXPI, closed 8/28/26 |
| TMRC | Being absorbed by USAR; buy the acquirer |
| NUAI (ex-NEHC) | Pivoted from helium to AI data centers |
| Jervois (JRVMF) | Delisted after Ch.11 6/30/25 |
| QS, SLDP | No robotics program; SLDP's +311% is a BMW/Samsung SDI EV story |
| PLTR as "robotics" | No confirmed program — defense-software adjacency only (still a tier-1 chain, on its own merits) |
| Suzhou Green Harmonic | Real Optimus reducer supplier; **no confirmed ticker** |
| RoboSense as "US lidar" | HK-only |
| SEO "humanoid stock" lists | Order sizes later disputed by Sanhua; treat as unverified |

## 7. How this trades — doctrine-honest

1. **Tier A is already live.** The tickers lane (armed 2026-09-04, production scorer, prereg frozen) trades NVDA/AAPL/AMZN, TSLA/META/AVGO, QQQ/IWM/GLD. Its universes are split by design and mid-window; **they are not edited for a theme.** If the robotics tape moves NVDA or TSLA into a setup, the lane already takes it.
2. **A robotics basket is not a universe edit, it is a new arm.** The multi lane is `STOPPED_ON_NULL` (2026-08-20) and its revive rule kill-lists *"try more names"* by name. The tickers lane's own pattern is the template: **a new pre-registration + a `shadow_only` arm running the production scorer over a fixed universe, WOULD_PLACE rows only, ≥20 signals / ≥15 sessions / random-entry null at MAX before any paper order.** Candidate universe for that prereg = §2 tier-1 + tight-but-priced-out: `ONDS BHP SIL AME MU MRVL TSM ARM` (the mega-caps are already covered). **Not built this session** — it is executor work on a live lane during the freeze window; queued for the 2026-09-29 checkpoint packet as a shadow (non-risk) item. Revoke by deleting the queue line.
3. **Equity (non-option) basket trading** of the tier-B names would be a *new lane* (different instrument, different exits, no 0DTE mechanics) and needs its own prereg. Nothing in this doc arms it.
4. **What shipped today, $0, reversible:** this doc; three screen JSONs + the universe JSON; the Alpaca watchlist `AI-Robotics-Chain` (delete = revoke); the memory note. No trading-path file was touched (the freeze fence covers `params.json` / fleet / filters / risk_gate / heartbeat_core — none edited).

## 8. Re-verify cadence

Spreads decay to noise in a day; re-run before quoting any number (RTH only, any non-core paper key via env vars):

```bash
python backtest/tools/weekly_universe_screen.py --symbols MP,USAR,UUUU,FCX,SYM,TER,ISRG,OUST,ONDS,BHP,SIL,APH,TKR,JBL --cap-dollars 1500 --params-path automation/state/multi/params.json --out analysis/multi-lane/universe-screen-robotics-rerun.json
```

Catalyst rows carry their source; the two China dates (11/10, 11/27) are the ones to re-check weekly — an extension announcement moves the whole L1 table the same hour.

---


## LAYER 1 — UPSTREAM: minerals, mining, refining, magnets

> Sonnet research fire 2026-09-08 ~14:10 ET, web-verified rows carry a source; UNVERIFIED rows are labelled. Market-cap buckets: mega >$200B / large $10–200B / mid $2–10B / small $300M–2B / micro <$300M.

### 1.1 Rare earths + NdFeB magnets (every robot joint has one)

| Ticker | Exch | Company | What it supplies into robots | Cap | Options | Bull | Risk | Next catalyst | Source |
|---|---|---|---|---|---|---|---|---|---|
| **MP** | NYSE | MP Materials | Mountain Pass → NdPr oxide → in-house NdFeB magnets (GM, Apple, DoD) | $10.1B large | Yes, weeklies, ~$340M/day | Only vertically-integrated US mine-to-magnet chain; DoD largest holder, $110/kg NdPr floor | 10X magnet plant scale-up execution; DoD-driven valuation | Q3 earnings ~10/29; first commercial GM magnet shipments Q4 | [cnbc](https://www.cnbc.com/2025/07/10/pentagon-to-become-largest-shareholder-in-rare-earth-magnet-maker-mp-materials.html) |
| **USAR** | NASDAQ | USA Rare Earth | Stillwater OK sintered-magnet plant (opened 3/26); Round Top HREE; Less Common Metals alloys | $4.4B mid | Yes, weeklies, ~$300M/day | Second US mine-to-magnet vertical; Serra Verde merger 9/3/26 | Pre-commercial, SPAC-derived, 52wk $11.45–$43.98 | Round Top 2028; magnet ramp | [wiki](https://en.wikipedia.org/wiki/USA_Rare_Earth) |
| **UUUU** | NYSE Am | Energy Fuels | White Mesa heavy-REE (Tb/Dy); **acquiring Vacuumschmelze $1.9B (6/23/26)** = Western magnet maker | $3.6B mid | Yes | Uranium cash funds REE pivot; VAC = instant magnet status | Integration; commercial HRE late 2027 | HRE plant build; VAC close | [cnbc](https://www.cnbc.com/2026/06/23/energy-fuels-to-buy-magnet-manufacturer-vacuumschmelze-gmbh.html) |
| LYC.AX / LYSCF | ASX / OTC | Lynas | Largest non-China separator; Seadrift TX HREE (DoD) | ~$13B large | No (OTC) | Decade-proven; $96M US offtake | No US listing; TX scope cut | FY26 TX facility | [mining.com](https://www.mining.com/web/lynas-rare-earths-signs-updated-contract-with-us-govt-for-texas-facility/) |
| NEO.TO / NOPMF | TSX / OTC | Neo Performance | Magnequench powders, magnets; EU plant → 5,000t | ~$1.2B small | No | Only non-China integrated magnet-materials w/ EU+Asia | China pricing controls inputs | 2–3 programs commercial by YE26 | [stockanalysis](https://stockanalysis.com/quote/tsx/NEO/market-cap/) |
| ILU.AX | ASX | Iluka | Eneabba integrated REE refinery (Dy/Tb) | A$2.8B small | No | A$1.65B govt financing; first OEM offtake | Commissioning mid-2027 | 75% built by YE26 | [amr](https://australianminingreview.com.au/issue/2026/01/australias-first-integrated-rare-earths-refinery/) |
| ARU.AX / ARAFF | ASX / OTC | Arafura | Nolans NdPr, FID approved | A$1.2B small | No | Hancock + KfW backing | Dilutive placements | Tranche-2 vote 2026 | [mining.com.au](https://mining.com.au/arafura-takes-off-with-350-million-placement-for-nolans-funding/) |
| **METC** | NASDAQ | Ramaco | Brook Mine WY coal-hosted REE; core = met coal | $950M small | Yes | Coal cash funds REE option; REalloys MOU | REE still byproduct-stage | Feasibility ongoing | [mining.com](https://www.mining.com/mulberry-industries-ramaco-resources-enter-rare-earth-offtake-mou-for-brook-mine/) |
| **NB** | NASDAQ | NioCorp | Elk Creek NE niobium/scandium/titanium/REE | $665M small | Thin | $10M DoW grant; EXIM $780M loan app | First output late 2029 | Financing close | [crux](https://www.cruxinvestor.com/posts/niocorp-developments-advancing-niobium-scandium-project-toward-2026-financing-construction) |
| **CRML** | NASDAQ | Critical Metals | Tanbreez Greenland HREE (→100%) | $1.1B small | Yes | 15-yr REalloys offtake; Greenland approvals | First ore Q4 2028+ | Pilot plant 8/26 | [cmc](https://www.criticalmetalscorp.com/greenland-government-approves-transfer-of-final-50-5-of-tanbreez-taking-critical-metals-corp-to-92-5-ownership/) |
| UCU.V / UURAF | TSXV / OTC | Ucore | Louisiana RapidSX HREE separation | micro UNVERIFIED | No | First US HREE separation outside a major | Chronic dilution | Machine #1 mid-2026 | [ucore](https://ucore.com/ucore-readies-for-louisiana-2026-heavy-rare-earth-element-processing/) |
| ARR.AX / ARRNF | ASX / OTC | American Rare Earths | Halleck Creek WY (2.63Bt) | micro UNVERIFIED | No | Scale | Feasibility only | 2026–27 drilling | [gnw](https://www.globenewswire.com/news-release/2026/06/18/3314184/0/en/american-rare-earths-provides-exploration-update-and-outlines-2026-2027-field-programs-across-u-s-project-portfolio.html) |
| ARA.TO | TSX | Aclara | Brazil/Chile ionic-clay HREE; LA separation planned | micro UNVERIFIED | No | Chile approval 6/26 | Financing-dependent | LA groundbreak late 2026 | [kalkine](https://kalkine.ca/news/mining/aclara-resources-stock-chile-green-light-clears-the-path-for-rare-earths) |
| TMRC | OTCQB | Texas Mineral Resources | 18.6% Round Top stake, being absorbed by USAR | ~$73M micro | No | — | **TRAP: being delisted, buy USAR** | Close Q3 2026 | [e-mj](https://www.e-mj.com/breaking-news/usa-rare-earth-to-acquire-texas-mineral-resources-corp/) |
| 600111.SS | Shanghai | China Northern Rare Earth | China's largest light-REE quota holder | ~$20B large | No (A-share) | Quota dominance | Not US-accessible | Earnings 10/16 | [stockanalysis](https://stockanalysis.com/quote/sha/600111/) |

Context only, not tradeable from the US: Shenghe Resources (300618.SZ, MP's historical China partner) and JL Mag (300748.SZ, top-3 NdFeB magnet maker for EV/robot).

### 1.2 Battery metals — lithium, nickel, cobalt, manganese, graphite (mobile robots)

| Ticker | Exch | Company | Supplies | Cap | Options | Bull | Risk | Source |
|---|---|---|---|---|---|---|---|---|
| **ALB** | NYSE | Albemarle | Chile brine + WA spodumene → hydroxide/carbonate | $15.1B large | Yes, weeklies | Lowest-cost global producer; +58% TTM | Lithium oversupply cycle | [adhoc](https://www.ad-hoc-news.de/boerse/news/corporate-news/albemarle-stock-climbs-as-lithium-prices-and-q2-sales-improve/69960312) |
| **SQM** | NYSE ADR | SQM | Atacama brine lithium | ~$20B large | Yes | Dominant brine position | Chile royalty/nationalization | [yahoo](https://finance.yahoo.com/quote/SQM/) |
| **LAC** | NYSE | Lithium Americas | Thacker Pass NV, GM JV, $2.23B DOE loan | UNVERIFIED | Yes | DOE + GM anchored | DOE 5% warrant dilution; 2026 capex | [gm](https://investor.gm.com/news-releases/news-release-details/gm-and-lithium-americas-develop-us-sourced-lithium-production) |
| PLL | NASDAQ | Piedmont Lithium | NC spodumene | $159M micro | Thin | Domestic option | Dilution | [stockopedia](https://www.stockopedia.com/share-prices/piedmont-lithium-NAQ:PLL/) |
| SLI | NYSE Am | Standard Lithium | Smackover DLE | $500M small | Thin | DLE + Exxon-adjacent | Pre-revenue | [macrotrends](https://www.macrotrends.net/stocks/charts/SLI/standard-lithium/market-cap) |
| SGML | NASDAQ | Sigma Lithium | Brazil spodumene, producing | $1.6B small (stale 4/26) | Yes | Low-cost quartile | Single asset | [cmc](https://companiesmarketcap.com/sigma-lithium/marketcap/) |
| NVX.AX / NVNXF | ASX / OTC | Novonix | NA synthetic graphite anode; Panasonic sample 6/26 | small UNVERIFIED | No | $103M 48C credit | Panasonic ramp 2H27 | [sec](https://www.sec.gov/Archives/edgar/data/1859795/000119312526198319/nvx-ex99_1.htm) |
| GLNCY | OTC ADR | Glencore | ~20% world cobalt + Cu/Ni | $80B large | Thin | Every battery metal | DRC/cobalt price | [cmc](https://companiesmarketcap.com/glencore/marketcap/) |
| TLOFF / TLO.TO | OTC / TSX | Talon Metals | Eagle nickel MI; Tamarack | micro UNVERIFIED | No | Lundin 19.9% | Feasibility H2'26 | [fool](https://www.fool.com/investing/stock-market/market-sectors/materials/metal-stocks/cobalt-stocks/) |
| **VALE** | NYSE | Vale | Nickel + copper (+ iron ore) | $60B large | Yes | Diversified scale | Brazil overhang | [cmc](https://companiesmarketcap.com/vale/marketcap/) |

Trap: Jervois Global delisted from ASX 6/30/25 after Chapter 11; ignore stale JRVMF quotes.

### 1.3 Copper (motor windings, wiring, data-center power)

| Ticker | Exch | Company | Supplies | Cap | Options | Bull | Risk | Source |
|---|---|---|---|---|---|---|---|---|
| **FCX** | NYSE | Freeport-McMoRan | Grasberg, Cerro Verde, Morenci | ~$109B large | Yes, weeklies, ~$788M/day | Best US-listed pure copper leverage; +44% YTD | Grasberg/Indonesia | [247](https://247wallst.com/investing/2026/09/07/freeport-mcmoran-has-ripped-44-in-2026-what-would-it-take-to-get-fcx-stock-up-to-100/) |
| **SCCO** | NYSE | Southern Copper | Mexico/Peru mine-smelt-refine | ~$160B large | Yes | $20.5B capex; $1.10 div | Family concentration, LatAm | [cmc](https://companiesmarketcap.com/southern-copper/marketcap/) |
| IVN.TO / IVPAF | TSX / OTC | Ivanhoe | Kamoa-Kakula, Kipushi (Ge byproduct) | ~$12B large | Thin OTC | Ge optionality | DRC | [macrotrends](https://www.macrotrends.net/stocks/charts/IVPAF/ivanhoe-mines/market-cap) |
| **TECK** | NYSE | Teck | QB2 copper + zinc | $34B large | Yes | QB2 ramped | Anglo merger structure | [cmc](https://companiesmarketcap.com/eur/teck-resources/marketcap/) |
| **BHP** | NYSE ADR | BHP | Escondida + nickel | $247B mega | Yes | Largest miner | Iron-ore dilutes copper | [cmc](https://companiesmarketcap.com/bhp-group/marketcap/) |
| **RIO** | NYSE ADR | Rio Tinto | 883kt Cu 2025, guiding 800–870kt 2026 | $157B large | Yes | Growing copper mix | Iron-ore core | [sec](https://www.sec.gov/Archives/edgar/data/0000863064/000162828026050377/rio-20260630_d2.htm) |
| ANTO.L | LSE | Antofagasta | Chile pure copper | large UNVERIFIED | No | Purest large-cap Cu | Chile only | [wiki](https://en.wikipedia.org/wiki/Antofagasta_plc) |
| **TMQ** | NYSE Am | Trilogy Metals | Ambler AK (South32 JV); **US govt 10% equity + warrants** | ~$0.5–0.8B small | Thin | Govt-backed; access road EO | No construction decision yet; headline-volatile | [cbs](https://www.cbsnews.com/news/us-ownership-stake-trilogy-metals-alaska/) |

### 1.4 Tungsten, titanium, antimony, gallium/germanium, silicon, HP quartz

| Ticker | Exch | Company | Supplies | Cap | Options | Bull | Risk | Source |
|---|---|---|---|---|---|---|---|---|
| **ALM** | NASDAQ | Almonty | Sangdong tungsten (S. Korea), revenue since 7/1/26 | small-mid UNVERIFIED (4x TTM) | Yes | Q2 rev +498%; $1.2B cash for Phase II | Momentum reversal; single mine | [adhoc](https://www.ad-hoc-news.de/boerse/news/corporate-news/resilient-almonty-industries-stock-jumps-on-q2-2026-profit-swing-and/69943926) |
| **UAMY** | NYSE Am | US Antimony | Only US antimony smelter | $770M small | Yes | Real domestic capacity; Perpetua tie | Antimony price mean-reversion | [ms](https://www.marketscreener.com/quote/stock/PERPETUA-RESOURCES-CORP-8415188/news/Riding-the-Antimony-Wave-4-Stocks-to-Watch-as-Prices-Hit-Record-Highs-MILIF-PPTA-UAMY-NVA-49152604/) |
| **PPTA** | NASDAQ | Perpetua | Stibnite ID antimony + gold; **EXIM $2.9B loan** | ~$2–3B mid | Yes | Largest US antimony govt commitment | Single asset, construction | [yahoo](https://finance.yahoo.com/markets/stocks/articles/perpetua-resources-tsx-ppta-down-160814101.html) |
| VNP.TO | TSX | 5N Plus | Western Ga/Ge/In producer | C$2.3B small-mid | No | Direct China-squeeze beneficiary; Q2 rev +28% | Suspension could be extended | [stockanalysis](https://stockanalysis.com/quote/tsx/VNP/market-cap/) |
| DQ | NYSE | Daqo | Chinese polysilicon | $833M small | Yes | Scale | **Value trap: solar-driven, <50% utilization** | [stockanalysis](https://stockanalysis.com/stocks/dq/) |
| GSM | NASDAQ | Ferroglobe | Western silicon metal | $610M small | Yes | Outside China | Thin margins | [stockanalysis](https://stockanalysis.com/stocks/gsm/market-cap/) |
| **IPX** | NASDAQ | IperionX | Low-carbon titanium powder (structural parts) | $893M small | Yes | DoW grants; ~200tpa by YE26 | Ramping from ~50tpa | [sws](https://simplywall.st/stocks/au/materials/asx-ipx/iperionx-shares/news/iperionx-asxipx-valuation-in-focus-after-fresh-usd-125m-dod) |
| S32.AX / SOUHY | ASX / OTC | South32 | Manganese (+ diversified) | $13B large | Thin | Mn scale | — | [cmc](https://companiesmarketcap.com/south32/marketcap/) |
| — | private | Sibelco / The Quartz Corp | HP quartz (Spruce Pine NC / Norway) | — | — | **Not investable** | — | [yahoo](https://finance.yahoo.com/news/high-purity-quartz-hpq-market-154000055.html) |

### 1.5 Silver, PGMs, helium, neon

| Ticker | Exch | Company | Supplies | Cap | Options | Note | Source |
|---|---|---|---|---|---|---|---|
| **HL** | NYSE | Hecla | Largest US silver (contacts) | $13.7B large | Yes | Most liquid silver leg | [macrotrends](https://macrotrends.net/stocks/charts/HL/hecla-mining/market-cap) |
| **PAAS** | NASDAQ | Pan American Silver | Diversified silver | large UNVERIFIED | Yes | Scale | [inn](https://investingnews.com/daily/resource-investing/precious-metals-investing/silver-investing/best-silver-stocks/) |
| **AG** | NYSE | First Majestic | 63% silver revenue | mid UNVERIFIED | Yes | Purest | [fool](https://www.fool.com/investing/stock-market/market-sectors/materials/silver-stocks/) |
| **SBSW** | NYSE | Sibanye Stillwater | PGMs + recycling; only US primary PGM (Montana) | $6.5B mid | Yes | Record H1'26 | [cmc](https://companiesmarketcap.com/sibanye-stillwater/marketcap/) |
| ANGPY | OTC ADR | Valterra Platinum | Largest primary PGM | ~$16B (stale 9/25) | Thin | Post-spin | [wiki](https://en.wikipedia.org/wiki/Valterra_Platinum) |
| **ASPI** | NASDAQ | ASP Isotopes (+Renergen) | SA helium; first liquid shipment Sept 2026 | small UNVERIFIED | Yes | New supply story | [mt](https://www.manilatimes.net/2026/08/20/tmt-newswire/globenewswire/asp-isotopes-inc-announces-that-renergen-limiteds-subsidiary-has-commenced-commissioning-of-liquid-helium-plant-in-south-africa/2409225/amp) |
| NUAI (ex-NEHC) | NASDAQ | New Era Helium | **TRAP: pivoted to AI data centers, no longer helium** | $231M micro (stale) | — | — | [bitget](https://www.bitget.com/wiki/nehc-stock) |

Neon: no investable public pure-play (Ingas/Cryoin private, Ukraine/Russia). Structural gap.

### 1.6 Upstream ETFs

| Ticker | Fund | AUM | Note | Source |
|---|---|---|---|---|
| **REMX** | VanEck Rare Earth/Strategic Metals | $1.9B | Top-5 ALB 8.0%, PLS 7.3%, MP 7.1%, Lynas 6.9%, China Northern 6.8% — ~40% China/Aus | [stockanalysis](https://stockanalysis.com/etf/remx/holdings/) |
| LIT | Global X Lithium & Battery | ~$1.5B | Broad lithium chain | [usnews](https://money.usnews.com/funds/etfs/natural-resources/global-x-lithium-battery-tech-etf/lit) |
| **COPX** | Global X Copper Miners | ~$7–8B | Largest copper-miner ETF | [globalx](https://www.globalxetfs.com/funds/copx) |
| ICOP | iShares Copper & Metals Mining | $463M | Smaller alt | [gsr](https://greenstocksresearch.com/copper-etfs/) |
| SIL | Global X Silver Miners | $11B (figure suspect, cross-check) | Silver miners | [investing](https://www.investing.com/etfs/silver-miners) |
| PPLT | abrdn Physical Platinum | $2.2B | Physical Pt | [abrdn](https://www.aberdeeninvestments.com/en-us/institutional/funds/view-all-funds/abrdn-physical-platinum-shares-etf-us0032601066) |
| PICK | iShares Global Metals & Mining Producers | UNVERIFIED | Broadest diversified miners | — |

### 1.7 Upstream — the 8 cleanest liquid, optionable expressions (researcher's ranking)

1. **MP** — only US mine-to-magnet vertical, DoD-anchored, deep weeklies.
2. **FCX** — copper leverage to both robot windings AND data-center power.
3. **UUUU** — uranium cash + REE + Western magnet maker via VAC.
4. **USAR** — second mine-to-magnet vertical; heaviest speculative options flow of the REE names.
5. **ALB** — largest, most liquid lithium.
6. **SCCO** — steadier copper leg.
7. **PPTA** — antimony with a real EXIM-financed project.
8. **HL** — most liquid silver.

### 1.8 Upstream traps
UCU/UURAF (chronic dilution) · ARRNF (sub-$0.30 OTC) · ARAA.F (thin, ownership just changed) · TMRC (being absorbed, buy USAR) · ARAFF OTC line (use ASX) · NUAI (not helium anymore) · E25.AX (A$62M, ASX-only) · DQ (solar value trap, not robotics).

### 1.9 Upstream catalysts, next 90 days
1. **11/10/2026 — China rare-earth export-control suspension expires** (Oct-2025 framework snaps back unless extended). Single biggest event for the whole REE table. [source](https://nextfinancial.substack.com/p/chinas-rare-earth-truce-expires-november)
2. **11/27/2026 — China Ga/Ge/Sb export-ban suspension expires**; military-end-user ban stays regardless. Hits VNP, UAMY, PPTA. [source](https://theoregongroup.com/commodities/gallium-germanium/china-lifts-export-ban-gallium-germanium-antimony/)
3. **~10/29 — MP Q3 earnings** + Q4 first commercial GM magnet shipments = the mine-to-magnet proof point. [source](https://www.tipranks.com/stocks/mp/earnings)
4. **10/16 — China Northern Rare Earth earnings**: read-through on quota/pricing before 11/10. [source](https://tradingeconomics.com/600111:ch)
5. **Section 232 copper**: 50% primary / 25% derivative through 12/31/2027; refined-copper exemption review Jan 2027 — leaks move FCX/SCCO. [source](https://www.congress.gov/crs-product/IN12614)
6. Operational: Almonty Sangdong Phase II; Trilogy 2026 field results; Ucore Machine #1 (may slip into window).


## LAYER 2 — MIDSTREAM: actuators, sensors, compute, batteries, structure, EMS, software

> Sonnet research fire 2026-09-08 ~14:15 ET. "Confirmed program" = a named customer/product found in a dated source this session; everything else is thematic exposure. Rows marked approx/UNVERIFIED were not re-quoted.

### 2.1 The joint — actuators, servo motors, reducers, ball screws, bearings

| Ticker | Exch | Company | Supplies | Confirmed program | Cap | US options | Thesis / risk | Source |
|---|---|---|---|---|---|---|---|---|
| **TKR** | NYSE | Timken | Precision bearings + actuator platform (bought Intelligent Machine Solutions) | "Precision motion platform for nearly all robotic actuator axes" (Industrial Motion ~34% of sales) | mid | Yes, weeklies | Diversified base derisks / robotics small % | [im](https://www.insidermonkey.com/blog/is-the-timken-company-tkr-a-good-stock-to-buy-now-1786631/) |
| **RRX** | NYSE | Regal Rexnord | Kollmorgen frameless servos, Portescap micro-motors, Thomson actuators, Berg gears | Automate 2026 Humanoid Forum; "key supplier to leading humanoid makers" (no name) | mid | Yes | Broadest Western single-vendor actuator BOM / no named flagship | [koll](https://www.kollmorgen.com/en-us/company/events/join-regal-rexnord-motion-brands-humanoid-robot-forum-automate-2026) |
| MOG.A | NYSE | Moog | Aerospace servoactuators → humanoid joints | Morgan Stanley Humanoid 100 | mid ~$9.7B | Yes | Premium reliability / rounding error vs defense | [photon](https://photoncap.net/p/investment-map-20-companies-in-the) |
| 6594.T | TYO | Nidec | BLDC/coreless motors; Tesla EV motor supplier | Positioned as global BLDC incumbent for humanoid | large ~$30B | No | #1 small precision motors / China undercutting | [photon](https://photoncap.net/p/investment-map-20-companies-in-the) |
| 6324.T | TYO | Harmonic Drive Systems | Strain-wave reducers, >70% global share | Core cobot reducer; humanoid "major long-term driver" | mid | No | IP moat / Green Harmonic 30–40% cheaper | [sws](https://simplywall.st/stocks/jp/capital-goods/tse-6324/harmonic-drive-systems-shares/news/humanoid-robotics-momentum-might-change-the-case-for-investi) |
| 6268.T | TYO | Nabtesco | Cycloidal reducers ~60% share | Reducer duopoly w/ HDS | mid | No | Near-monopoly / same China risk | same |
| 1590.TW | TWSE | Hiwin | Ball screws, harmonic reducers, roller screws (2026) | MS Humanoid 100; robotics >10% of rev guided 2026 | mid | No | Broadest Taiwan linear-motion line / cross-strait | [digitimes](https://www.digitimes.com/news/a20251117PD220/robot-hiwin-technologies-component-taiwan-supply-chain.html) |
| 6481.T / 6471.T | TYO | THK / NSK | Linear guides, ball screws, bearings | No named humanoid program found | mid | No | Incumbents / weakest robot news flow | UNVERIFIED |
| 601689.SS | SSE | Tuopu | Tier-0.5 linear + rotary actuator assembly | **Confirmed Optimus supplier; Tesla = 35–40% of revenue** | large ~$15B | No | Most direct Optimus exposure / single-customer | [36kr](https://eu.36kr.com/en/p/3780414717129481) |
| 002050.SZ / 2050.HK | SZSE/HK | Sanhua | Joint-module assembly | **~$685M Musk order Oct 2025**, Mexico deliveries 2026 (Sanhua disputed a separate rumored figure) | large ~$16B | No | China+Mexico footprint / disputed order sizes | [36kr](https://eu.36kr.com/en/p/3510288514980998) |
| 000920.SZ | SZSE | Zhaowei | Dexterous-hand drive modules | Goldman named 1 of 9 key suppliers | small-mid | No | Hardest sub-component / thin disclosure | [gs](https://robottoday.com/article/what-goldman-sachs-discovered-about-china-s-humanoid-robots) |
| 002472.SZ | SZSE | Shuanghuan (Fine Motion) | Robot gearboxes | Analyst-rated | mid | No | Subsidiary-level | [aastocks](https://www.aastocks.com/en/stocks/news/aafn-con/NOW.1529424/popular-news/AAFN) |
| — | pre-IPO? | Suzhou Green Harmonic | Harmonic reducers ~25% share, targeting 60% of Optimus reducers at 30–40% below Japan | Confirmed Optimus reducer supplier | **listing UNVERIFIED** | No | Direct disruptor to HDS/Nabtesco / cannot trade without a ticker | [36kr](https://eu.36kr.com/en/p/3780414717129481) |

### 2.2 Sensors — lidar, vision, force/torque, IMU

| Ticker | Exch | Company | Supplies | Confirmed program | Cap | Options | Thesis / risk | Source |
|---|---|---|---|---|---|---|---|---|
| **OUST** | NASDAQ | Ouster | Digital lidar + Stereolabs cameras, "Physical AI" stack | No single humanoid OEM named | small ~$1–2B, +130% YTD | Yes | Purest US lidar-for-robots / unprofitable, July raise | [247](https://247wallst.com/investing/2026/07/03/which-robotics-supply-chain-stock-has-dominated-in-2026-ouster-aeva-or-vishay-precision-group/) |
| **AEVA** | NASDAQ | Aeva | 4D FMCW lidar-on-chip | NVIDIA + Daimler Truck programs; humanoid not yet revenue | small, +81% YTD | Yes | Differentiated FMCW / pre-scale | same |
| **HSAI** | NASDAQ ADR | Hesai | Lidar (largest by units) | Robotics = named diversification | mid ~$3B+ | Yes | Volume leader / China-ADR risk | [sa](https://stockanalysis.com/stocks/hsai/) |
| 2498.HK | HK | RoboSense | Robot-branded lidar | — | mid | No | No US line | UNVERIFIED |
| VPG | NYSE | Vishay Precision | Strain-gauge force sensors → F/T sensing | Top 2026 performer +216%; humanoid pipeline unconfirmed | small | Thin | Direct F/T tech / thin OI | [247](https://247wallst.com/investing/2026/07/03/which-robotics-supply-chain-stock-has-dominated-in-2026-ouster-aeva-or-vishay-precision-group/) |
| **NOVT** | NASDAQ | Novanta | "Varo" force/torque sensor marketed for humanoids | Product named; no OEM verified | mid | Yes | Direct product line / small base | [li](https://www.linkedin.com/posts/humanoid-robotics-technology_novanta-varo-forcetorque-sensor-for-humanoids-activity-7431707268590592000-BdM-) |
| **CGNX** | NASDAQ | Cognex | Machine vision for factory/warehouse robots; Nvidia edge-AI camera | Industrial incumbent | large $10.5B, +75% YTD | Yes, weeklies | Vision-guidance incumbent / 39x P/E, Keyence | [sa](https://stockanalysis.com/stocks/cgnx/) |
| TDY / AME / ST | NYSE | Teledyne / Ametek / Sensata | Cameras, instruments, position/current sensors | Broad, no named program | large/large/mid | Yes | Diversified / least pure | UNVERIFIED |
| **ON** | NASDAQ | onsemi | Hyperlux HDR image sensors for robot vision | Named w/ Sony as humanoid-vision incumbents | large | Yes, weeklies | Current-gen named product / semis cycle | [ran](https://roboticsandautomationnews.com/2026/03/17/stmicroelectronics-and-leopard-imaging-launch-nvidia-jetson-ready-vision-module-for-humanoid-robots/99773/) |
| **STM** | NYSE ADR | STMicro | **Jetson-ready multi-camera humanoid module w/ Leopard Imaging (Mar 2026)** | Confirmed product, no end-OEM | large | Yes | Dated Jetson product / EU auto drag | same |
| **SONY** | NYSE ADR | Sony | #1 CMOS image sensors; **$6.3B TSMC sensor-manufacturing split for "physical AI"** | Confirmed TSMC deal | large | Yes | #1 share + TSMC capacity / diluted by games/music | [tt](https://www.techtimes.com/articles/323736/20260810/sony-splits-sensor-manufacturing-tsmc-63b-deal-capture-physical-ai-market.htm) |

### 2.3 Compute, memory, foundry, connectors, power semis

| Ticker | Exch | Company | Supplies | Confirmed program | Cap | Options | Thesis / risk | Source |
|---|---|---|---|---|---|---|---|---|
| **NVDA** | NASDAQ | NVIDIA | Jetson Thor (2,000 TFLOPS), Isaac/GR00T/Omniverse | **Adopters: Agility, Amazon Robotics, Boston Dynamics, Caterpillar, Figure, Hexagon, Medtronic, Meta; evaluating 1X, Deere, OpenAI, Physical Intelligence. Optimus does NOT use NVIDIA robot silicon.** | mega | Yes, weeklies | Owns the reference stack / vertical-integration (Tesla) is the bear case | [nv](https://nvidianews.nvidia.com/news/nvidia-blackwell-powered-jetson-thor-now-available-accelerating-the-age-of-general-robotics) |
| **QCOM** | NASDAQ | Qualcomm | Dragonwing IQ10 (CES 2026) edge robot compute | Efficient alternative below Jetson envelope | large | Yes, weeklies | Mid-tier robots (AMR/cobot) / handset mix | [exo](https://exoswan.com/edge-ai-stocks/) |
| **NXPI** | NASDAQ | NXP | Motor-control MCUs; **acquired Ambarella (closed 8/28/26)** for edge-vision | M&A framed on robotics vision | large ~$60B | Yes | Bought edge vision / integration | [sa](https://siliconangle.com/2026/07/31/nxp-reportedly-talks-acquire-vehicle-chip-supplier-ambarella/) |
| ~~AMBA~~ | — | Ambarella | **ACQUIRED by NXP, delisted — remove from lists** | — | — | — | — | [sh](https://www.startuphub.ai/exit-events/ambarella-acquisition-2026) |
| IFX.DE / IFNNY | XETRA/OTC | Infineon | Power semis, XENSIV sensors, AURIX; **~$500 semi content per humanoid** (disclosed); NVIDIA physical-AI collab (Mar 2026) | Explicit $/unit figure | large ~€50B | No (ADR thin) | Only chipmaker with a per-unit number / ADR illiquid | [ifx](https://www.infineon.com/press-release/2025/INFXX202508-134) |
| TXN | NASDAQ | Texas Instruments | Motor-drive analog | Broad | large | Yes, weeklies | Analog margins / no named program | UNVERIFIED |
| **ADI** | NASDAQ | Analog Devices | Motor control; tactile + ToF reference designs on **NVIDIA Isaac Sim** | Confirmed Isaac Sim collab | large | Yes, weeklies | Dated NVIDIA collab / cycle | [prn](https://www.prnewswire.com/news-releases/synopsys-showcases-nvidia-partnership-impact-and-ecosystem-innovation-at-gtc-2026-302715123.html) |
| ARM / AVGO / MRVL / MCHP | NASDAQ | Arm / Broadcom / Marvell / Microchip | CPU IP / custom ASIC + networking / connectivity / MCUs | Indirect | large–mega | Yes | Royalty or infra exposure / not robot-specific | UNVERIFIED |
| **MU** | NASDAQ | Micron | DRAM/NAND; **CEO: humanoids need ~10x the memory of a self-driving car** | Explicit CEO thesis | large | Yes, weeklies | Quantified memory content / memory cycle | [247](https://247wallst.com/investing/2026/08/11/humanoid-robots-need-10x-the-memory-of-a-self-driving-car-micron-is-positioned-to-win/) |
| 000660.KS | KRX | SK Hynix | DRAM/HBM | 1 of 3 scaled DRAM makers | large | No | Same thesis / Korea access | [ap](https://www.advisorperspectives.com/articles/2026/06/25/sk-hynix-micron-solidify-memory-chip-runaway-star-ai) |
| **TSM** | NYSE ADR | TSMC | Foundry for every robot SoC; Amkor 10-yr packaging; Sony sensor split | Confirmed partnerships | mega | Yes, weeklies | The foundry / Taiwan tail | [amkr](https://ir.amkor.com/news-releases/news-release-details/tsmc-and-amkor-technology-announce-long-term-partnership) |
| AMAT / LRCX / KLAC / ASML | NASDAQ | Semicap | Deposition/etch/process control/EUV | AMAT–TSMC packaging R&D confirmed | large–mega | Yes, weeklies | AI-capex tailwind / cyclical | [sws](https://simplywall.st/stocks/us/semiconductors/nasdaq-amat/applied-materials/news/does-applied-materials-expanded-ai-packaging-push-with-tsmc) |
| **AMKR** | NASDAQ | Amkor | Advanced packaging; **TSMC 10-yr partnership, Arizona, $2.5–3B 2026 capex** | Confirmed | mid | Yes | CoWoS overflow / concentration | same |
| **APH** | NYSE | Amphenol | Connectors, cable, sensors; **Q2'26 record $8.8B, +55% YoY** | UBS-named humanoid connector beneficiary | large | Yes, weeklies | Every robot needs connectors / priced for perfection | [fool](https://www.fool.com/investing/2026/08/08/wall-street-sees-a-multi-trillion-dollar-humanoid/) |
| **TEL** | NYSE | TE Connectivity | Connectors; **Q3'26 record $5.16B, +14%** | Same UBS thesis | large | Yes, weeklies | Connector duopoly / same | same |
| — | private | Molex (Koch) | "Humanoid Robotics Connectors" product line | Named line | — | — | **Not investable** | [molex](https://www.molex.com/en-us/industries-applications/humanoid-robotics/humanoid-robotics-connectors) |

### 2.4 Batteries for mobile robots

| Ticker | Exch | Company | Confirmed program | Cap | Options | Verdict | Source |
|---|---|---|---|---|---|---|---|
| 373220.KS | KRX | LG Energy Solution | **Supply contracts with Tesla, Boston Dynamics, Figure; preparing Optimus initial-run cells** | large | No | The single most-confirmed humanoid battery supplier; Korea-only | [ked](https://www.kedglobal.com/batteries/newsView/ked202607020005) |
| 300750.SZ / 3750.HK | SZSE/HK | CATL | **Galbot S1 humanoid on CATL cells**; Tesla cell supplier | mega | No | Largest battery maker / no US line | [cnc](https://carnewschina.com/2026/06/16/battery-showdown-catl-byd-and-panasonic-spark-2-20-billion-usd-energy-war/) |
| 6752.T | TYO | Panasonic | **Solid-state samples for robots/drones FY-Mar-2027** | large | No | Only dated solid-state-for-robots roadmap | [gn](https://gulfnews.com/business/energy/panasonic-to-debut-next-gen-solid-state-batteries-for-robots-1.500273784) |
| **ENVX** | NASDAQ | Enovix | Silicon-anode; robotics on target list, no OEM | small-mid | Yes | Architecture fit / pre-scale | [idtechex](https://www.idtechex.com/en/research-report/batteries-for-humanoid-robots/1174) |
| AMPX | NYSE | Amprius | High-silicon cells; "AI and Robotics" product page | micro-small | Thin | Purest small-cap positioning / no flagship | [amprius](https://amprius.com/ai-and-robotics) |
| QS | NYSE | QuantumScape | **No commercial production; robotics = "future opportunity"** | mid | Yes, weeklies | **HYPE, no program** | [iev](https://insideevs.com/news/786661/quantumscape-solid-state-battery-production-eagle-cto-interview-2026/) |
| SLDP | NASDAQ | Solid Power | **BMW/Samsung SDI EV story, +311% YTD; zero robotics program** | small | Yes | **Mis-mapped onto robotics by retail** | [electrek](https://electrek.co/2025/10/31/bmw-samsung-sdi-join-forces-all-solid-state-ev-batteries/) |
| 006400.KS / 300014.SZ | KRX / SZSE | Samsung SDI / EVE Energy | Indirect / no named program | large | No | Access-blocked | UNVERIFIED |

### 2.5 Structure, machining, factory automation, integrators

| Ticker | Exch | Company | Role | Cap | Options | Note | Source |
|---|---|---|---|---|---|---|---|
| 6861.T | TYO | Keyence | Sensors/vision; **BOTZ #1 holding 10.8%** | mega | No | Richest sensor franchise; Tokyo-only | [botz](https://finance.yahoo.com/quote/BOTZ/holdings/) |
| 6954.T / 6506.T / 6645.T / 6503.T | TYO | Fanuc / Yaskawa / Omron / Mitsubishi Electric | Industrial arms, servo "monopoly", FA control | large | No | Deepest install bases; Tokyo-only | [botz](https://finance.yahoo.com/quote/BOTZ/holdings/) |
| SIEGY / ABBNY | OTC ADR | Siemens / ABB | Automation + digital twin / industrial robots (ABB orders $11.3B, +32%) | mega/mega | Thin | ADR liquidity is the blocker | UNVERIFIED |
| **ROK** | NYSE | Rockwell | Allen-Bradley + FactoryTalk | large | Yes, weeklies | Reshoring capex / cyclical, market skeptical | [cmc](https://www.cmcmarkets.com/en-gb/opto/is-symbotic-the-most-promising-of-these-industrial-automation-stocks) |
| EMR | NYSE | Emerson | Process automation | large | Yes, weeklies | Least robot-specific | UNVERIFIED |
| **SYM** | NASDAQ | Symbotic | AI warehouse systems; ARMS Innovations acq. 2026 | large $26B | Yes, weeklies | Purest US warehouse-AMR integrator / Walmart concentration | [lv](https://logisticsviewpoints.com/2026/07/06/warehouse-automation-is-increasingly-becoming-operational-intelligence-what-symbotics-acquisition-of-arms-innovations-signals-about-the-future-of-distribution/) |
| **TER** | NASDAQ | Teradyne | Owns Universal Robots + MiR; **Robotics $100M Q2'26, +33%, 5th growth qtr** | large $58B | Yes, weeklies | Only US semicap-test + cobot OEM / segment ~$400M vs core | [trr](https://www.therobotreport.com/teradyne-robotics-revenue-rises-33-year-over-year-in-q2/) |
| HXGN / HEXA-B.ST | Stockholm | Hexagon | Metrology; **named Jetson Thor early adopter** | large | Thin | Direct NVIDIA / access | [nv](https://nvidianews.nvidia.com/news/nvidia-blackwell-powered-jetson-thor-now-available-accelerating-the-age-of-general-robotics) |
| PRLB / XMTR | NYSE/NASDAQ | Proto Labs / Xometry | Rapid machining, marketplace | small | Thin | Prototyping class / no contract | UNVERIFIED |
| VLD | NYSE | Velo3D | Metal AM | micro | Very thin | **Verify going-concern before any trade** | UNVERIFIED |
| HXL / 3402.T | NYSE / TYO | Hexcel / Toray | Carbon fiber | mid | Yes / No | Aerospace-first | UNVERIFIED |

### 2.6 Contract manufacturers — who actually builds robots

| Ticker | Exch | Company | Confirmed program | Cap | Options | Source |
|---|---|---|---|---|---|---|
| **JBL** | NYSE | Jabil | **Worldwide production partner for Apptronik Apollo humanoid** — the only US EMS with a named humanoid contract | large | Yes, weeklies | [appt](https://apptronik.com/news-collection/apptronik-and-jabil-collaborate-to-scale-production) |
| 2317.TW | TWSE | Foxconn | **Deploying own Isaac GR00T humanoids on Houston GB300 line; Vietnam humanoid trial production Sept 2026, official Nov 2026** | large | No | [asm](https://www.assemblymag.com/articles/99628-foxconn-to-deploy-humanoid-robots-on-production-line-at-houston-ai-server-plant) |
| CLS / FLEX / SANM | NYSE/NASDAQ | Celestica / Flex / Sanmina | **No named humanoid contract found** — AI-server thesis, not robotics | mid-large | Yes | UNVERIFIED |
| 2382.TW / 3231.TW / 4938.TW / 0285.HK / 002475.SZ | TW/HK/SZ | Quanta / Wistron / Pegatron / BYD Electronics / Luxshare | AI-server ODM or cluster adjacency; no named robot contract | large | No | UNVERIFIED |

### 2.7 Software / model layer

| Entity | Investable via | Confirmed | Source |
|---|---|---|---|
| NVIDIA Isaac / GR00T / Omniverse | NVDA | Foxconn Houston line; ADI Isaac Sim assets; reference stack | [tm](https://technologymagazine.com/news/foxconn-nvidia-and-tesla-to-power-humanoid-robot-revolution) |
| DeepMind Gemini Robotics | GOOGL | Google = named Apptronik investor | [forbes](https://www.forbes.com/sites/johnkoetsier/2026/02/11/apptronik-scores-935-million-hits-top-3-for-humanoid-robotics-funding/) |
| PTC Onshape → OpenUSD → Isaac Sim | PTC | Dated 2026 workflow | [gnw](https://www.globenewswire.com/news-release/2026/03/16/3256763/0/en/NVIDIA-and-Global-Industrial-Software-Giants-Bring-Design-Engineering-and-Manufacturing-Into-the-AI-Era.html) |
| Synopsys (Ansys 2026 R1, Omniverse) | SNPS (Ansys no longer separate) | Dated release | [prn](https://www.prnewswire.com/news-releases/synopsys-launches-ansys-2026-r1-to-re-engineer-engineering-with-joint-solutions-and-ai-powered-products-302711215.html) |
| Skild AI ($14B, Jan 2026; NVIDIA/Samsung/SoftBank/Bezos) | NVDA indirect | — | [sa](https://siliconangle.com/2026/01/14/robot-software-startup-skild-ai-raises-1-4b-round-backed-nvidia-jeff-bezos/) |
| Physical Intelligence ($2.4B) | not investable | — | [sf](https://startupfundraising.com/ai-physical-intelligence-world-models-simulation-fundraising) |
| Covariant | AMZN (acquihired 2024, immaterial) | — | same |
| Palantir | PLTR | **No confirmed robotics program — thematic adjacency only** | UNVERIFIED |

### 2.8 Midstream — researcher's 12 most direct liquid US expressions
NVDA · TER · APH · TEL · MU · QCOM · STM · ON · TKR · RRX · JBL · MP. Caveat: only LGES / Tuopu / Sanhua / Foxconn / Jabil carry named, dollar-quantified humanoid contracts; the US large caps are broad exposure.

### 2.9 Midstream hype-with-no-program
QS (future opportunity only) · SLDP (EV story mislabelled) · PLTR (no program) · Green Harmonic (no confirmed ticker) · RoboSense (no US line) · SEO-aggregator "humanoid stock" lists (order sizes later disputed by Sanhua).

### 2.10 Midstream catalysts, next 90 days
1. **10/28 — Tesla Q3 (after close)**: the Optimus number-or-slip event; moves Tuopu/Sanhua/LGES sentiment.
2. **11/30–12/3 — NVIDIA GTC DC**: physical-AI track, Jetson/Isaac/GR00T adopter announcements.
3. **11/10 — China rare-earth control suspension expires** (see Layer 1).
4. **Sept 2026 — Foxconn Vietnam humanoid trial production** (official Nov).
5. **Agility SPAC (CCXI → AGLT)**: no vote date set as of late Aug; proxy filing is the next step.


## LAYER 3 — DOWNSTREAM: the robot makers, deployers, autonomy, ETFs — and Acuity

> Sonnet research fire 2026-09-08 ~14:15 ET; caps/volumes mostly stockanalysis.com same-day where marked verified.

### 3.0 Acuity — what it is and is not

**J's "Acuity" = Acuity Inc (NYSE: AYI, ex-Acuity Brands).** The other hits are non-public micro-startups: Acuity Robotics (Leeds UK, 4 staff, inspection robots) and Acuity AI (private, robot training-data vendor). Neither has a ticker.

| AYI fact | Value (verified 2026-09-08) | Source |
|---|---|---|
| Market cap / price | $9.74B / $327.64 | [sa](https://stockanalysis.com/stocks/ayi/) |
| Avg volume | ~350–540K sh/day (~$115–165M) | [cnbc](https://www.cnbc.com/quotes/AYI) |
| Options | Monthly chain exists; weeklies UNVERIFIED | [barchart](https://www.barchart.com/stocks/quotes/AYI/volatility-greeks) |
| Last print (Q3 FY26) | Beat + raise, **+17.5% on the day**; sales $1,198M (+1.6%), adj EPS $5.31 | [yahoo](https://finance.yahoo.com/markets/stocks/articles/acuity-inc-ayi-q3-2026-190031641.html) |
| Growth engine | Acuity Intelligent Spaces (Distech BMS + Atrius + QSC AV): **$303.5M, +14.9% y/y, 25.1% margin** | same |
| **Next earnings** | **~Sept 30–Oct 1, 2026** pre-market, consensus EPS ~$5.44 | [mb](https://www.marketbeat.com/stocks/NYSE/AYI/earnings/) |
| FY26 guide | Rev $4.8B, non-GAAP EPS $19.75 | same |

**Honest angle:** AYI is software-defined *building* intelligence (HVAC, lighting, occupancy, AV) with an "AI maximalist" management. It is **not a robotics company** and will not move on Optimus/Waymo headlines. Management even flagged data-center construction as a **headwind** for the legacy lighting segment (crowding out labor/materials) [yahoo](https://finance.yahoo.com/markets/stocks/articles/acuity-brands-inc-q2-2026-164615971.html). Watch it as an AI-adjacent earnings-momentum name around 9/30, on its own list, not in the robotics basket.

### 3.1 Humanoid / general-purpose robots

| Ticker | Exch | Company | Builds | Cap | Options | Thesis / risk | Next catalyst | Source |
|---|---|---|---|---|---|---|---|---|
| **TSLA** | NASDAQ | Tesla | Optimus + robotaxi | mega ~$1.4T | Yes, weeklies + dailies | Optionality + narrative velocity / 2026 Optimus output likely "low thousands" vs 50–100K target | Q3 earnings 10/28 | [electrek](https://electrek.co/2026/07/02/musk-shuts-down-optimus-4d-chess-theory/) |
| **XPEV** | NYSE ADR | XPeng | IRON humanoid (76 DoF, Turing chip); **automated IRON line commissioned Sept 2026** | large | Yes | First to commission a humanoid line / mass production YE26 unproven | YE26 mass production | [cnev](https://cnevpost.com/2026/09/08/xpeng-opens-iron-humanoid-robot-production-line/) |
| 9880.HK | HK | UBTech | Walker; 1H26 humanoid sales +268%, rev +104% | mid-large | No | No US line | Order flow | [inv](https://www.investing.com/equities/ubtech-robotics) |
| 688836.SS | STAR | Unitree | G1/H1; **IPO 8/19/26 +629% intraday, ~$50B** | large | No | First pure humanoid IPO / mainland-only, Stock Connect pending | Connect inclusion | [cnbc](https://www.cnbc.com/2026/08/19/china-backflipping-robot-maker-unitree-jumps-shanghai-ipo.html) |
| 005380.KS | KRX | Hyundai | Owns Boston Dynamics; Atlas productized, 2026 fleet to Hyundai + DeepMind | mega | ADR thin | Immaterial to Hyundai P&L | Atlas deployments | [bbg](https://www.bloomberg.com/news/articles/2026-01-05/hyundai-unveils-new-humanoid-robot-to-work-in-its-car-factories) |
| 277810.KQ | KOSDAQ | Rainbow Robotics | Hubo-2; Samsung-controlled | mid ~$6.4B | No | Pure-play / Korea-only, huge vol | RB-01K Army delivery YE26 | [inv](https://www.investing.com/equities/rainbow-robotics) |
| 066570.KS / 7203.T / HMC | KRX/TYO/NYSE | LG / Toyota / Honda | CLOiD (Nvidia stack) / T-HR3 / E4 (w/ Sony) | large–mega | HMC, TM yes | Immaterial | Pilots | UNVERIFIED |
| — | private | Agibot | HK IPO targeted ~Q3 2026, HK$40–50B; Tencent/BYD/Hillhouse | — | — | Not yet tradeable | IPO | [tfn](https://techfundingnews.com/top-humanoid-robot-startups-2026-funding/) |
| — | private | Figure AI | $39B; NVDA/MSFT/INTC/QCOM/Bezos/OpenAI backers; secondaries below mark | — | — | Trade via backers | — | [sacra](https://sacra.com/c/figure-ai/) |
| — | private → **CCXI/AGLT** | Agility Robotics | Digit; **SPAC w/ Churchill XI, $2.5B pre-money (6/24/26)**; 98% task success at Amazon Sumner; Toyota, GXO, Schaeffler, Mercado Libre | pending | pending | **First pure-play US-listed humanoid once closed** / vote date not set | SPAC close 2H26 | [tc](https://techcrunch.com/2026/06/24/agility-robotics-plans-to-go-public-via-spac-in-a-2-5b-deal/) |
| **MBLY** | NASDAQ | Mobileye | ADAS + robotaxi + **acquired Mentee Robotics (humanoid) 2026** | mid $7.2B | Yes | Only ADAS+robotaxi+humanoid combo / −39% YTD, churn | Robotaxi 2027 | [sa](https://stockanalysis.com/stocks/mbly/) |
| NVDA / MSFT / AMZN / INTC | NASDAQ | Proxies | Figure/Agility/1X backers; Jetson stack | mega | Yes, weeklies | Picks-and-shovels; AMZN deploys Digit + own fleet | Earnings | [gw](https://www.geekwire.com/2026/digit-maker-agility-robotics-to-go-public-in-2-5b-deal-heres-what-the-filings-say-about-its-finances/) |

### 3.2 Industrial, warehouse, service

| Ticker | Exch | Company | Builds | Cap | Options | Thesis / risk | Next catalyst | Source |
|---|---|---|---|---|---|---|---|---|
| **SYM** | NASDAQ | Symbotic | Walmart warehouse robotics; rev +22%, GAAP profitable | $26.4B large | Yes, weeklies | 400-system pipeline / concentration, multiple | **Earnings 11/23** | [sa](https://stockanalysis.com/stocks/sym/) |
| **TER** | NASDAQ | Teradyne | Universal Robots + MiR; +253% 12mo | $58.2B large | Yes, weeklies | Detroit hub, Flex/Vention / semicap-test cyclicality | Earnings | [sa](https://stockanalysis.com/stocks/ter/) |
| **ROK** | NYSE | Rockwell | Factory automation | large | Yes, weeklies | Software-first / market skeptical | Earnings | — |
| ABBNY / 6954.T / 6506.T / 6861.T / 6645.T | OTC/TYO | ABB / Fanuc / Yaskawa / Keyence / Omron | Big-Four industrial robots + vision | large–mega | Thin/No | Orders $11.3B (ABB) / access | Earnings | [botz](https://stockanalysis.com/etf/botz/holdings/) |
| **CGNX** | NASDAQ | Cognex | AI machine vision; +75% YTD, raised guide | $10.5B large | Yes, weeklies | Nvidia edge camera / 39x | Earnings | [sa](https://stockanalysis.com/stocks/cgnx/) |
| **ZBRA** | NASDAQ | Zebra | Scanners, RFID, "Frontline AI" | $16.5B large | Yes | Re-rated / — | Earnings | [sa](https://stockanalysis.com/stocks/zbra/) |
| ~~IRBT~~ | OTC IRBTQ | iRobot | **DEAD — Ch.11 12/14/25, equity to Picea Robotics, $5M cap. Remove.** | — | — | — | — | [axios](https://www.axios.com/local/boston/2025/12/15/irobot-roomba-bankruptcy-chapter-11-picea-chinese-manufacturer-bedford-massachusetts) |
| **SERV** | NASDAQ | Serve Robotics | Sidewalk delivery + Diligent healthcare; rev +578% | $425M small | Yes, weeklies, active | Uber Eats/DoorDash / **31–34% of float short**, burn ≈ revenue | Q3 print | [sa](https://stockanalysis.com/stocks/serv/) |
| RR | NASDAQ | Richtech | Hospitality robots | $395M small | Yes | Retail attention / **$900M ATM shelf, 64x EV/S, late 10-Q (8/14)** | 10-Q | [sa](https://seekingalpha.com/article/4861466-richtech-robotics-is-a-dilution-trap-rating-downgrade) |
| KSCP | NASDAQ | Knightscope | Security robots; Q2 rev $9M +228% | $34M micro | Thin | **Going-concern doubt, $8.2M cash** | Raise | [st](https://www.stocktitan.net/sec-filings/KSCP/10-q-knightscope-inc-quarterly-earnings-report-fbc7f68863f4.html) |
| KITT | NASDAQ | Nauticus | Subsea robots | micro | Thin | **$2.0M cash, burning $14M/half** | Financing | [sa](https://stockanalysis.com/stocks/kitt/) |
| PDYN | NASDAQ | Palladyne AI (ex-Sarcos) | Pivoted to AI software + defense; rev guide $24–27M | small | Yes | No longer a hardware story | Contracts | [sa](https://seekingalpha.com/article/4909453-palladyne-stock-ai-autonomy-and-the-relentless-wolfpack) |
| ~~BGRY~~ | — | Berkshire Grey | **Private (SoftBank 2023). Remove.** | — | — | — | — | [spac](https://www.spacinsider.com/news/headline-post/berkshire-grey-bgry-to-be-acquired-by-softbank) |
| OCDO.L / AUTO.OL / KGX.DE | LSE/Oslo/FRA | Ocado / AutoStore / Kion (Dematic) | Warehouse automation | mid-large | No | Kroger + Sobeys pulled back (Ocado) | — | [ms](https://www.marketscreener.com/news/ocado-gets-350-million-payment-after-kroger-culls-robotic-warehouse-network-ce7d51dcda89f024) |
| **GXO** | NYSE | GXO | 3PL deploying Digit + AMRs | mid | Yes | Real deployer / logistics cycle | Disclosures | [ob](https://www.originofbots.com/news/agility-robotics-digit-moves-beyond-pilots-now-handling-real-warehouse-work-at-amazon-toyota-and-gxo) |
| WMT | NYSE | Walmart | Symbotic anchor customer | mega | Yes, weeklies | Immaterial to WMT | — | — |

### 3.3 Surgical

| Ticker | Company | Builds | Cap | Options | Note | Source |
|---|---|---|---|---|---|---|
| **ISRG** | Intuitive Surgical | da Vinci 5; 246 placements Q2 vs 180; procedure guide 14–16% | $125B large | Yes, weeklies | Leader / Hugo, Mako RPS, Ottava now cleared | [sa](https://stockanalysis.com/stocks/isrg/) |
| PRCT | Procept | HYDROS; 1,036 systems | $1.2B small | Yes | **−63% on Q4 miss + rebate change; class actions** | [sa](https://stockanalysis.com/stocks/prct/) |
| STXS / RBOT / MBOT | Stereotaxis / Vicarious / Microbot | Niche | micro | Thin | GenesisX (STXS) / pre-commercial | — |
| MDT / SYK / JNJ | Medtronic Hugo / Stryker Mako RPS / J&J Ottava (**FDA de novo 2026, 10 procedure types**) | mega | Yes, weeklies | Hugo "doesn't move the needle" yet (CEO) | [mtd](https://www.medtechdive.com/news/JJ-submits-FDA-de-novo-Ottava-robot-general-surgery/808976/) |

### 3.4 Autonomy — robotaxi, trucking, drones, defense

| Ticker | Company | Builds | Cap | Options | Thesis / risk | Next | Source |
|---|---|---|---|---|---|---|---|
| **GOOGL** | Waymo | Robotaxi; **Denver/San Diego/Tampa launched 9/1**; 1M rides/wk YE26 target | mega | Yes, weeklies | Losses buried in Other Bets | DC/Dallas/Houston/Orlando/San Antonio | [tc](https://techcrunch.com/2026/09/01/waymo-accelerates-robotaxi-expansion-with-launches-in-denver-san-diego-and-tampa/) |
| **AUR** | Aurora | Driverless Class-8; 2026 capacity contracted; 200 trucks YE26 | $13.0B large, 15.4M sh/day | Yes, weeklies | Burn ~$225M/qtr | Fleet scaling | [sa](https://stockanalysis.com/stocks/aur/) |
| **PONY** / **WRD** | Pony AI / WeRide | China robotaxi; PONY rev +691%, 3,000 vehicles 2026 | $3.2B / $2.0B mid | Yes | China overhang | Fleet | [sa](https://stockanalysis.com/stocks/pony/) |
| BIDU / UBER / LYFT | Apollo Go / platforms | **Uber+Apollo Go driverless live in Dubai**; London testing | large–mega | Yes, weeklies | Economics unclear | Dubai/London | [uber](https://investor.uber.com/news-events/news/press-release-details/2026/Uber-Launches-Baidus-Fully-Driverless-Apollo-Go-in-Dubai-Establishing-the-First-Multi-Partner-Autonomous-Network-Globally/default.aspx) |
| KDK | Kodiak AI | Driverless trucks + GD defense JV; AMD compute | $788M small | Yes | FCF −$160–170M | Long-haul launch | [sa](https://stockanalysis.com/stocks/kdk/) |
| **AVAV** / **KTOS** | AeroVironment / Kratos | Autonomous drones; $464.8M Army laser (AVAV); backlog >$2B (KTOS) | $7.5B / $9.1B mid | Yes, weeklies | −31% / −38% YTD sentiment reset | Awards | [sa](https://stockanalysis.com/stocks/avav/) |
| RCAT / ONDS / DPRO / UMAC | Red Cat / Ondas / Draganfly / Unusual Machines | Retail-momentum drones; ONDS **30M sh/day, +217%**; UMAC +355%; DPRO +152% | $1.3B / $4.4B / $0.2B / $1.3B | Yes, weeklies | Extended; "lock in profits" headlines | Aran close Q3 (ONDS) | [sa](https://stockanalysis.com/stocks/onds/) |
| **PLTR** | Palantir | Defense-autonomy software; FY26 guide $7.65B | $413B mega | Yes, weeklies | Priced richly; no confirmed robotics program | Earnings | [sa](https://stockanalysis.com/stocks/pltr/) |
| — | Anduril | Private, ~$100B talks | — | — | No proxy | — | [tc](https://techcrunch.com/2026/07/24/anduril-reportedly-in-talks-to-raise-funding-at-100b-valuation-more-than-3x-last-years-mark/) |

### 3.5 ETFs

| Ticker | Fund | AUM | Top holdings | ER | Source |
|---|---|---|---|---|---|
| **HUMN** | Roundhill Humanoid Robotics | $86M | TSLA 8.5%, UBTech 6.7%, XPEV 4.6%, NVDA 4.6%, Rainbow 4.5% (47) | 0.75% | [rh](https://www.roundhillinvestments.com/etf/humn/) |
| **KOID** | KraneShares Humanoid & Physical AI | $334M | MerQube index | 0.69% | [ks](https://kraneshares.com/etf/koid/) |
| WDRN | WisdomTree Physical AI, Humanoids & Drones | UNVERIFIED (June 2026 launch) | — | 0.45% | [yahoo](https://finance.yahoo.com/markets/stocks/articles/did-wisdomtree-physical-ai-robotics-042131193.html) |
| **BOTZ** | Global X Robotics & AI | $3.41B | Keyence 10.8%, NVDA 9.4%, ABB 9.1%, Fanuc 7.8%, ISRG 6.1% | 0.68% | [gx](https://www.globalxetfs.com/funds/botz) |
| ROBO / ROBT / ARTY (ex-IRBO) / ARKQ | broad automation / Nasdaq AI+robotics / equal-weight AI / ARK active | large / $725M / ~$0.5B / large | — | 0.95 / 0.65 / 0.47 / 0.75% | [mq](https://metaqsol.com/en/archives/48250) |

### 3.6 Downstream — researcher's 15 liquid headline-movers
TSLA · NVDA · PLTR · GOOGL · ISRG · TER · SYM · AUR · CGNX · KTOS · AVAV · MBLY · ONDS · RCAT · SERV.

### 3.7 Retail-momentum small caps — the facts
SERV 31–34% of float short, burn ≈ revenue · RR $900M ATM shelf, late 10-Q · KSCP going-concern · DPRO M&A-funded · UMAC +355%, verify deal financing · KITT $2M cash.

### 3.8 Biggest 60-day moves
UMAC +355% · ONDS +217% · DPRO +152% · TER +206% (12mo) · RCAT +56% · Unitree +629% IPO day · CGNX +42% · KSCP −41% · PRCT −43% · AVAV/KTOS −31/−38% · MBLY −35% · IRBT −99% (terminal).

### 3.9 Downstream catalysts, next 90 days
| Date | Event | Names |
|---|---|---|
| ~9/30–10/1 | AYI earnings (AIS checkpoint) | AYI |
| 10/28 | Tesla Q3 — Optimus ramp, robotaxi | TSLA, HUMN/KOID |
| 11/23 | Symbotic FQ4 — Walmart pipeline | SYM |
| 2H26 | Agility SPAC close (CCXI → AGLT) | AGLT, HUMN, KOID |
| by 12/31 | XPeng IRON mass production start | XPEV, UBTech, Unitree |


---

## Update log

- **2026-09-08** — created (J directive 14:00 ET). 3 Sonnet research fires + live 8%-gate screen at 14:14–14:19 ET over 137 names; Alpaca watchlist `AI-Robotics-Chain` created; shadow-arm prereg queued in FUTURE-IMPROVEMENTS. No trading-path edits (freeze intact).
