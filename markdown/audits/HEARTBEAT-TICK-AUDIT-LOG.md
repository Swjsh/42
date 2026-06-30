# Heartbeat Tick Audit — Rolling Log

> **Rolling reverse-chronological log** (newest first) of the per-day heartbeat tick-alignment audit
> produced by `backtest/autoresearch/heartbeat_tick_audit.py`. The generator still writes a per-date
> `HEARTBEAT-TICK-AUDIT-{date}.md` snapshot when it runs; those dated snapshots fold UP into this log
> and age out. **Retention: keep the last ~10 days here**; older entries live in git history.
>
> **What "MISALIGNED-CRITICAL" means:** the heartbeat acted on a `claimed_spy` price that diverged
> materially from the closed-bar close — the R1 closed-bar fix (shipped 2026-05-14, v15.1) is supposed
> to keep this at zero. A non-zero critical count is the signal to investigate via that day's per-tick CSV.

---

## 2026-06-29

**0 of 0 live-trading ticks (0%) MISALIGNED-CRITICAL.**

| Classification | Ticks | % |
|---|---:|---:|
| ALIGNED | 0 | 0.0% |
| MISALIGNED-BENIGN | 0 | 0.0% |
| MISALIGNED-CRITICAL | 0 | 0.0% |
| STALE_PAUSED | 0 | 0.0% |
| NO_DATA | 0 | 0.0% |
| NO_BAR | 0 | 0.0% |
| **TOTAL** | **0** | 100% |

Critical ticks: none. **R1:** ✅ fix held (zero critical).
Files: `automation\state\heartbeat-tick-audit-2026-06-29.{csv,json}`, source log `(missing)`, source CSV `backtest\data\spy_5m_2026-05-19_2026-06-29.csv`.

---

## 2026-06-26

**0 of 0 live-trading ticks (0%) MISALIGNED-CRITICAL.**

| Classification | Ticks | % |
|---|---:|---:|
| ALIGNED | 0 | 0.0% |
| MISALIGNED-BENIGN | 0 | 0.0% |
| MISALIGNED-CRITICAL | 0 | 0.0% |
| STALE_PAUSED | 0 | 0.0% |
| NO_DATA | 0 | 0.0% |
| NO_BAR | 0 | 0.0% |
| **TOTAL** | **0** | 100% |

Critical ticks: none. **R1:** ✅ fix held (zero critical).
Files: `automation\state\heartbeat-tick-audit-2026-06-26.{csv,json}`, source log `(missing)`, source CSV `backtest\data\spy_5m_2026-05-19_2026-06-26.csv`.

---

## 2026-06-25

**8 of 32 live-trading ticks (25%) MISALIGNED-CRITICAL.**

| Classification | Ticks | % |
|---|---:|---:|
| ALIGNED | 10 | 13.7% |
| MISALIGNED-BENIGN | 14 | 19.2% |
| MISALIGNED-CRITICAL | 8 | 11.0% |
| STALE_PAUSED | 9 | 12.3% |
| NO_DATA | 32 | 43.8% |
| NO_BAR | 0 | 0.0% |
| **TOTAL** | **73** | 100% |

Critical ticks (8):

| tick_id | fire_at | decision | claimed_spy | closed_close | divergence | reason |
|---:|---|---|---:|---:|---:|---|
| 12 | 10:06:02 | SKIP_TV_DATA_STALE | 737.33 | 733.240 | +4.0900 | spy=737.33 ribbon=unknown vix=17.88(falling) bear=0/10 bull=0/11 htf=null | TV_F |
| 13 | 10:09:01 | SKIP_TV_DATA_STALE | 737.33 | 733.240 | +4.0900 | spy=737.33 ribbon=UNAVAIL vix=17.88(falling_stale) bear=0/10 bull=0/11 htf=null  |
| 35 | 11:15:01 | SKIP_TV_DATA_STALE | 737.33 | 732.970 | +4.3600 | spy=737.33 ribbon=null vix=17.88(falling) bear=0/10 bull=0/11 htf=null | TV_MCP_ |
| 36 | 11:18:01 | SKIP_TV_DATA_STALE | 737.33 | 732.970 | +4.3600 | spy=737.33 ribbon=?c(?) vix=17.88(falling) bear=0/10 bull=0/11 htf=? | Alpaca ba |
| 41 | 11:33:01 | SKIP_TV_DATA_STALE | 737.33 | 734.290 | +3.0400 | spy=737.33 ribbon=null vix=17.88(falling) bear=0/10 bull=0/11 htf=null | TV_MCP_ |
| 46 | 11:48:02 | HOLD | 737.33 | 734.770 | +2.5600 | spy=737.33 ribbon=null vix=17.88(falling) bear=0/10 bull=0/11 htf=null | inside_ |
| 58 | 12:25:02 | SKIP_TV_DATA_STALE | 737.3 | 734.440 | +2.8599 | spy=737.3 ribbon=1.8c(BEAR) vix=17.88(cached) bear=5/10 bull=4/11 htf=null | TV+ |
| 69 | 12:59:52 | HOLD | 735.7 | 732.700 | +3.0000 | spy=735.7 ribbon=5.3c(BEAR) vix=17.88(falling) bear=5/10 bull=4/11 htf=null | ri |

**R1:** 🔴 fix may NOT be working — 8 critical (25.0% of live); heartbeat may still be reading in-progress bars. (Note: most criticals here are `SKIP_TV_DATA_STALE` — stale TV feed, not an in-progress-bar read.)
Files: `automation\state\heartbeat-tick-audit-2026-06-25.{csv,json}`, source log `automation\state\logs\heartbeat-2026-06-25.log`, source CSV `backtest\data\spy_5m_2026-05-19_2026-06-25.csv`.

---

## 2026-06-24

**4 of 78 live-trading ticks (5%) MISALIGNED-CRITICAL.**

| Classification | Ticks | % |
|---|---:|---:|
| ALIGNED | 12 | 10.7% |
| MISALIGNED-BENIGN | 62 | 55.4% |
| MISALIGNED-CRITICAL | 4 | 3.6% |
| STALE_PAUSED | 0 | 0.0% |
| NO_DATA | 34 | 30.4% |
| NO_BAR | 0 | 0.0% |
| **TOTAL** | **112** | 100% |

Critical ticks (4):

| tick_id | fire_at | decision | claimed_spy | closed_close | divergence | reason |
|---:|---|---|---:|---:|---:|---|
| 76 | 13:18:02 | ENTER_BEAR | 733.81 | 734.790 | -0.9800 | spy=733.81 ribbon=115c(BEAR) vix=18.79(rising) bear=10/10 bull=N/A htf=null | ri |
| 77 | 13:21:02 | HOLD | 736.48 | 733.820 | +2.6600 | spy=736.48 ribbon=36c(MIXED) vix=18.79(rising) bear=4/10 bull=7/11 htf=null | ri |
| 80 | 13:30:01 | HOLD_DEV | 736.48 | 732.160 | +4.3200 | spy=736.48 ribbon=36c(MIXED) vix=18.79(rising) bear=4/10 bull=7/11 htf=null | ri |
| 81 | 13:33:02 | HOLD_DEV | 736.48 | 732.160 | +4.3200 | spy=736.48 ribbon=36c(MIXED) vix=18.79(rising) bear=4/10 bull=7/11 htf=null | be |

**R1:** 🔴 fix may NOT be working — 4 critical (5.1% of live); heartbeat may still be reading in-progress bars.
Files: `automation\state\heartbeat-tick-audit-2026-06-24.{csv,json}`, source log `automation\state\logs\heartbeat-2026-06-24.log`, source CSV `backtest\data\spy_5m_2026-05-19_2026-06-24.csv`.

---

## 2026-06-23

**0 of 0 live-trading ticks (0%) MISALIGNED-CRITICAL.**

| Classification | Ticks | % |
|---|---:|---:|
| ALIGNED | 0 | 0.0% |
| MISALIGNED-BENIGN | 0 | 0.0% |
| MISALIGNED-CRITICAL | 0 | 0.0% |
| STALE_PAUSED | 0 | 0.0% |
| NO_DATA | 0 | 0.0% |
| NO_BAR | 0 | 0.0% |
| **TOTAL** | **0** | 100% |

Critical ticks: none. **R1:** ✅ fix held (zero critical).
Files: `automation\state\heartbeat-tick-audit-2026-06-23.{csv,json}`, source log `(missing)`, source CSV `backtest\data\spy_5m_2026-05-19_2026-06-23.csv`.

---

## 2026-06-22

**1 of 79 live-trading ticks (1%) MISALIGNED-CRITICAL.**

| Classification | Ticks | % |
|---|---:|---:|
| ALIGNED | 20 | 19.6% |
| MISALIGNED-BENIGN | 58 | 56.9% |
| MISALIGNED-CRITICAL | 1 | 1.0% |
| STALE_PAUSED | 1 | 1.0% |
| NO_DATA | 22 | 21.6% |
| NO_BAR | 0 | 0.0% |
| **TOTAL** | **102** | 100% |

Critical ticks (1):

| tick_id | fire_at | decision | claimed_spy | closed_close | divergence | reason |
|---:|---|---|---:|---:|---:|---|
| 42 | 11:36:02 | HOLD | 738.52 | 744.600 | -6.0800 | spy=738.52 ribbon=18c(BEAR) vix=16.85(flat) bear=6/10 bull=7/11 htf=BEAR | 11:30 |

**R1:** 🟡 fix partial — 1 critical (1.3% of live); investigate via per-tick CSV.
Files: `automation\state\heartbeat-tick-audit-2026-06-22.{csv,json}`, source log `automation\state\logs\heartbeat-2026-06-22.log`, source CSV `backtest\data\spy_5m_2026-05-19_2026-06-22.csv`.

---

## 2026-06-18

**0 of 32 live-trading ticks (0%) MISALIGNED-CRITICAL.**

| Classification | Ticks | % |
|---|---:|---:|
| ALIGNED | 9 | 17.0% |
| MISALIGNED-BENIGN | 23 | 43.4% |
| MISALIGNED-CRITICAL | 0 | 0.0% |
| STALE_PAUSED | 1 | 1.9% |
| NO_DATA | 20 | 37.7% |
| NO_BAR | 0 | 0.0% |
| **TOTAL** | **53** | 100% |

Critical ticks: none. **R1:** ✅ fix held (zero critical).
Files: `automation\state\heartbeat-tick-audit-2026-06-18.{csv,json}`, source log `automation\state\logs\heartbeat-2026-06-18.log`, source CSV `backtest\data\spy_5m_2026-05-19_2026-06-18.csv`.
