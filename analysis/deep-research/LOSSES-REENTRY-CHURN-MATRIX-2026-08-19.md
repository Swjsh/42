# Smaller losses — RE-ENTRY & CHURN full matrix

> Lane: **fine-tuning smaller losses / re-entry and churn.** Dataset: [`analysis/recommendations/trade-matrix.json`](../recommendations/trade-matrix.json) — 303 closed round trips, 35 trading days (2026-06-26..2026-08-19), 5 real-fills arms.
> **Scope: analysis and proposal only.** Nothing armed, no `params*.json` touched, no orders. Every recommendation below ships as a pre-registered hypothesis with a kill criterion.

---

## Verdict — WEAK

**A re-entry cooldown does recover money, but not enough of it to survive its own robustness tests, and the biggest-looking version of it destroys the right tail this book lives on.**

| | |
|---|---|
| Best cell by raw delta | **30 min · any contract · after any exit** → net **+$2,734** |
| Why it is REJECTED | it destroys **23 winners worth $2,636 = 16.8% of every winner dollar in the book**, including the #1 and #2 single winners; **top-3 days = 88.6%** of the effect; p=0.067 vs a random-removal null |
| Cell actually recommended | **3 min · same symbol · only after a STOP** → gross **+$1,024**, net **+$1,031**, after fees+exit-slippage **+$1,175** |
| Production today | **no cooldown at all** on the core path |
| Honest read | the mechanism is real and narrow; the **dollars are carried by one day (69%)** |

---

## 1. What production actually does today (the baseline cell)

- **Core ribbon path: ZERO cooldown.** The quality-lock / re-entry suppression was deleted in full on J's written order 2026-07-02 (`setup/scripts/heartbeat_core.py`, comment block *"re-entry lock: DELETED"*). Its ABSENCE is pinned by `test_tz_quality_lock_2026_07_02.py`. An ENTER after a same-setup stop routes straight to `_execute`.
- **Only two things stand between a stop-out and an immediate re-entry:** the broker FLAT-verify (`fb.is_flat_spy_options`) and a 180-second per-(arm,symbol) **entry claim** (`ENTRY_CLAIM_TTL_SEC = 180`) — which is a *duplicate-order* race guard, not a cooldown; it is explicitly documented as never blocking "a legitimate re-entry minutes later".
- **Extra-signal (watcher) lane only:** since 2026-07-20 a **same-trigger-bar** guard per (arm, setup) — `exit_actuator.same_bar_cooldown_active`. Bar-boundary, not a duration, and it did not exist for the first ~2/3 of this dataset.

> That same comment block pre-registers this exact study: *"Any future cooldown gate ships only with A/B evidence."* This document is that A/B.

---

## 2. The raw answer to the question

**How much net P&L is lost to re-entries within N minutes of a stop on the same or adjacent contract?**

Every entry is matched to the nearest *preceding stop-out on the same arm*. Gap in minutes, relation by contract. Net = fee-adjusted USD.

| gap after a stop | same symbol | adjacent ±$1 | adjacent ±$2 | same side, far | opposite side | row total |
|---|---|---|---|---|---|---|
| **<3 min** | n=21 · $-783 | n=3 · $49 | — | — | n=4 · $-271 | **n=28 · $-1,006** |
| **3-5 min** | n=5 · $-58 | n=3 · $583 | — | — | — | **n=8 · $526** |
| **5-10 min** | n=1 · $-81 | n=4 · $-294 | — | — | n=5 · $-353 | **n=10 · $-728** |
| **10-15 min** | n=1 · $-28 | n=5 · $-688 | — | — | n=2 · $-29 | **n=8 · $-745** |
| **15-30 min** | n=11 · $530 | n=12 · $-794 | — | — | n=12 · $-539 | **n=35 · $-803** |
| >=30 min | n=27 · $1,685 | n=43 · $-504 | n=13 · $-4 | n=52 · $138 | n=74 · $-310 | **n=209 · $1,005** |

- **Post-stop re-entry within 30 min on the same or ±$1 contract: n=66, net $-1,563.98.**
- Tightened to 3 minutes: n=24, net $-734.77.
- The single worst cell is **same symbol, under 3 minutes: n=21, net $-783.34** — this is the M3 churn family, and it is the only cell where the mechanism is unambiguous (you were just stopped out of *this exact contract* and bought it straight back).
- Everything at **≥30 min is net POSITIVE ($1,005)**, which is what makes a cooldown look attractive — and is also the first thing to be suspicious of, because time-since-last-exit is not randomly assigned.

> ⚠️ **These raw numbers OVERSTATE what a cooldown recovers.** Blocking trade B changes the clock for trade C. Every simulated cell below re-runs the sequence with blocked trades removed from the chain, so a blocked trade never sets a cooldown of its own. The cascaded numbers are smaller.

---

## 3. The full matrix — 90 cells

Cooldown {0, 3, 5, 10, 15, 30} min × scope {same symbol, ±$1, ±$2, same side, any contract} × trigger {after a stop, after a loss, after any exit}. Simulated sequentially per arm; a blocked trade never happens and therefore never starts a cooldown of its own. **Decidable with zero look-ahead** — every input (prior exit time, prior exit reason, prior contract) is known at the instant the rule would fire.

Production row (cooldown 0) is **marked ⬛** and is identical in all 15 scope×trigger combinations: net $-1,940, WR 23.1%, avg loss $-75.51, worst $-664.69, max DD $-5,263.

| cd | scope | trigger | kept | blkd | net $ | Δ gross | Δ net | Δ net+slip | WR | avg loss | worst loss | max DD | winners killed | winner $ killed | loser $ killed | top-day share | top-trade share |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 ⬛ | same_symbol | stop_exit | 303 | 0 | -1,940 | +0 | **+0** | +0 | 23.1% | -75.51 | -664.69 | -5,263 | 0 | 0 | 0 | — | — |
| 0 ⬛ | same_symbol | loss_exit | 303 | 0 | -1,940 | +0 | **+0** | +0 | 23.1% | -75.51 | -664.69 | -5,263 | 0 | 0 | 0 | — | — |
| 0 ⬛ | same_symbol | any_exit | 303 | 0 | -1,940 | +0 | **+0** | +0 | 23.1% | -75.51 | -664.69 | -5,263 | 0 | 0 | 0 | — | — |
| 0 ⬛ | adjacent1 | stop_exit | 303 | 0 | -1,940 | +0 | **+0** | +0 | 23.1% | -75.51 | -664.69 | -5,263 | 0 | 0 | 0 | — | — |
| 0 ⬛ | adjacent1 | loss_exit | 303 | 0 | -1,940 | +0 | **+0** | +0 | 23.1% | -75.51 | -664.69 | -5,263 | 0 | 0 | 0 | — | — |
| 0 ⬛ | adjacent1 | any_exit | 303 | 0 | -1,940 | +0 | **+0** | +0 | 23.1% | -75.51 | -664.69 | -5,263 | 0 | 0 | 0 | — | — |
| 0 ⬛ | adjacent2 | stop_exit | 303 | 0 | -1,940 | +0 | **+0** | +0 | 23.1% | -75.51 | -664.69 | -5,263 | 0 | 0 | 0 | — | — |
| 0 ⬛ | adjacent2 | loss_exit | 303 | 0 | -1,940 | +0 | **+0** | +0 | 23.1% | -75.51 | -664.69 | -5,263 | 0 | 0 | 0 | — | — |
| 0 ⬛ | adjacent2 | any_exit | 303 | 0 | -1,940 | +0 | **+0** | +0 | 23.1% | -75.51 | -664.69 | -5,263 | 0 | 0 | 0 | — | — |
| 0 ⬛ | same_side_any | stop_exit | 303 | 0 | -1,940 | +0 | **+0** | +0 | 23.1% | -75.51 | -664.69 | -5,263 | 0 | 0 | 0 | — | — |
| 0 ⬛ | same_side_any | loss_exit | 303 | 0 | -1,940 | +0 | **+0** | +0 | 23.1% | -75.51 | -664.69 | -5,263 | 0 | 0 | 0 | — | — |
| 0 ⬛ | same_side_any | any_exit | 303 | 0 | -1,940 | +0 | **+0** | +0 | 23.1% | -75.51 | -664.69 | -5,263 | 0 | 0 | 0 | — | — |
| 0 ⬛ | any_contract | stop_exit | 303 | 0 | -1,940 | +0 | **+0** | +0 | 23.1% | -75.51 | -664.69 | -5,263 | 0 | 0 | 0 | — | — |
| 0 ⬛ | any_contract | loss_exit | 303 | 0 | -1,940 | +0 | **+0** | +0 | 23.1% | -75.51 | -664.69 | -5,263 | 0 | 0 | 0 | — | — |
| 0 ⬛ | any_contract | any_exit | 303 | 0 | -1,940 | +0 | **+0** | +0 | 23.1% | -75.51 | -664.69 | -5,263 | 0 | 0 | 0 | — | — |
| 3 | same_symbol | stop_exit | 288 | 15 | -909 | +1,024 | **+1,031** | +1,175 | 23.3% | -74.51 | -664.69 | -4,712 | 3 | 97 | -1,127 | 0.69 | 0.29 |
| 3 | same_symbol | loss_exit | 287 | 16 | -914 | +1,019 | **+1,026** | +1,176 | 23.0% | -74.51 | -664.69 | -4,716 | 4 | 101 | -1,127 | 0.70 | 0.29 |
| 3 | same_symbol | any_exit | 283 | 20 | -933 | +999 | **+1,007** | +1,173 | 22.3% | -74.85 | -664.69 | -4,721 | 7 | 120 | -1,128 | 0.71 | 0.29 |
| 3 | adjacent1 | stop_exit | 285 | 18 | -958 | +974 | **+982** | +1,144 | 22.8% | -74.75 | -664.69 | -4,782 | 5 | 167 | -1,149 | 0.73 | 0.30 |
| 3 | adjacent1 | loss_exit | 284 | 19 | -962 | +969 | **+977** | +1,144 | 22.5% | -74.75 | -664.69 | -4,786 | 6 | 171 | -1,149 | 0.73 | 0.30 |
| 3 | adjacent1 | any_exit | 278 | 25 | -1,056 | +874 | **+884** | +1,080 | 21.6% | -75.30 | -664.69 | -4,760 | 10 | 295 | -1,179 | 0.81 | 0.34 |
| 3 | adjacent2 | stop_exit | 285 | 18 | -958 | +974 | **+982** | +1,144 | 22.8% | -74.75 | -664.69 | -4,782 | 5 | 167 | -1,149 | 0.73 | 0.30 |
| 3 | adjacent2 | loss_exit | 284 | 19 | -962 | +969 | **+977** | +1,144 | 22.5% | -74.75 | -664.69 | -4,786 | 6 | 171 | -1,149 | 0.73 | 0.30 |
| 3 | adjacent2 | any_exit | 277 | 26 | -1,064 | +865 | **+876** | +1,076 | 21.3% | -75.30 | -664.69 | -4,760 | 11 | 304 | -1,179 | 0.81 | 0.34 |
| 3 | same_side_any | stop_exit | 285 | 18 | -958 | +974 | **+982** | +1,144 | 22.8% | -74.75 | -664.69 | -4,782 | 5 | 167 | -1,149 | 0.73 | 0.30 |
| 3 | same_side_any | loss_exit | 284 | 19 | -962 | +969 | **+977** | +1,144 | 22.5% | -74.75 | -664.69 | -4,786 | 6 | 171 | -1,149 | 0.73 | 0.30 |
| 3 | same_side_any | any_exit | 276 | 27 | -999 | +930 | **+941** | +1,146 | 21.4% | -75.34 | -664.69 | -4,760 | 11 | 304 | -1,245 | 0.76 | 0.32 |
| 3 | any_contract | stop_exit | 283 | 20 | -617 | +1,314 | **+1,323** | +1,493 | 23.7% | -74.88 | -664.69 | -4,441 | 3 | 97 | -1,420 | 0.54 | 0.22 |
| 3 | any_contract | loss_exit | 282 | 21 | -622 | +1,309 | **+1,318** | +1,493 | 23.4% | -74.88 | -664.69 | -4,445 | 4 | 101 | -1,420 | 0.54 | 0.23 |
| 3 | any_contract | any_exit | 271 | 32 | -590 | +1,336 | **+1,350** | +1,577 | 22.1% | -75.81 | -664.69 | -4,351 | 10 | 249 | -1,599 | 0.53 | 0.22 |
| 5 | same_symbol | stop_exit | 282 | 21 | -981 | +949 | **+958** | +1,147 | 23.0% | -76.04 | -664.69 | -4,750 | 5 | 135 | -1,094 | 0.63 | 0.31 |
| 5 | same_symbol | loss_exit | 280 | 23 | -1,001 | +929 | **+939** | +1,139 | 22.5% | -76.04 | -664.69 | -4,769 | 7 | 155 | -1,094 | 0.64 | 0.32 |
| 5 | same_symbol | any_exit | 274 | 29 | -1,057 | +870 | **+882** | +1,110 | 21.9% | -77.04 | -664.69 | -4,824 | 10 | 224 | -1,107 | 0.68 | 0.34 |
| 5 ❌ | adjacent1 | stop_exit | 276 | 27 | -2,281 | -354 | **-341** | -107 | 22.1% | -77.06 | -664.69 | -4,820 | 9 | 1,368 | -1,027 | -1.77 | -1.87 |
| 5 ❌ | adjacent1 | loss_exit | 274 | 29 | -2,301 | -374 | **-361** | -115 | 21.5% | -77.06 | -664.69 | -4,839 | 11 | 1,387 | -1,027 | -1.67 | -1.77 |
| 5 ❌ | adjacent1 | any_exit | 265 | 38 | -2,286 | -363 | **-346** | -57 | 20.8% | -77.99 | -664.69 | -4,718 | 15 | 1,562 | -1,215 | -1.74 | -1.85 |
| 5 ❌ | adjacent2 | stop_exit | 276 | 27 | -2,281 | -354 | **-341** | -107 | 22.1% | -77.06 | -664.69 | -4,820 | 9 | 1,368 | -1,027 | -1.77 | -1.87 |
| 5 ❌ | adjacent2 | loss_exit | 274 | 29 | -2,301 | -374 | **-361** | -115 | 21.5% | -77.06 | -664.69 | -4,839 | 11 | 1,387 | -1,027 | -1.67 | -1.77 |
| 5 ❌ | adjacent2 | any_exit | 264 | 39 | -2,295 | -372 | **-355** | -61 | 20.5% | -77.99 | -664.69 | -4,718 | 16 | 1,571 | -1,215 | -1.70 | -1.80 |
| 5 ❌ | same_side_any | stop_exit | 276 | 27 | -2,281 | -354 | **-341** | -107 | 22.1% | -77.06 | -664.69 | -4,820 | 9 | 1,368 | -1,027 | -1.77 | -1.87 |
| 5 ❌ | same_side_any | loss_exit | 274 | 29 | -2,301 | -374 | **-361** | -115 | 21.5% | -77.06 | -664.69 | -4,839 | 11 | 1,387 | -1,027 | -1.67 | -1.77 |
| 5 ❌ | same_side_any | any_exit | 264 | 39 | -2,295 | -372 | **-355** | -61 | 20.5% | -77.99 | -664.69 | -4,718 | 16 | 1,571 | -1,215 | -1.70 | -1.80 |
| 5 ❌ | any_contract | stop_exit | 274 | 29 | -2,004 | -77 | **-64** | +176 | 22.6% | -76.87 | -664.69 | -4,542 | 8 | 1,361 | -1,297 | -9.46 | -10.03 |
| 5 ❌ | any_contract | loss_exit | 272 | 31 | -2,023 | -97 | **-83** | +169 | 22.1% | -76.87 | -664.69 | -4,561 | 10 | 1,380 | -1,297 | -7.27 | -7.70 |
| 5 | any_contract | any_exit | 260 | 43 | -1,876 | +45 | **+64** | +375 | 21.2% | -77.89 | -664.69 | -4,299 | 15 | 1,563 | -1,627 | 9.45 | 10.02 |
| 10 | same_symbol | stop_exit | 279 | 24 | -1,249 | +680 | **+691** | +941 | 22.9% | -75.55 | -664.69 | -4,750 | 6 | 659 | -1,350 | 1.24 | 0.76 |
| 10 | same_symbol | loss_exit | 275 | 28 | -1,232 | +695 | **+708** | +976 | 22.5% | -76.09 | -664.69 | -4,733 | 8 | 678 | -1,386 | 1.21 | 0.74 |
| 10 | same_symbol | any_exit | 267 | 36 | -1,242 | +681 | **+698** | +1,004 | 21.7% | -77.25 | -664.69 | -4,742 | 12 | 752 | -1,450 | 1.23 | 0.75 |
| 10 | adjacent1 | stop_exit | 270 | 33 | -676 | +1,249 | **+1,264** | +1,553 | 24.1% | -75.91 | -664.69 | -4,240 | 5 | 768 | -2,032 | 0.68 | 0.51 |
| 10 | adjacent1 | loss_exit | 266 | 37 | -659 | +1,264 | **+1,281** | +1,588 | 23.7% | -76.48 | -664.69 | -4,223 | 7 | 787 | -2,068 | 0.67 | 0.50 |
| 10 | adjacent1 | any_exit | 253 | 50 | -605 | +1,312 | **+1,335** | +1,709 | 22.5% | -77.99 | -664.69 | -4,083 | 13 | 973 | -2,308 | 0.64 | 0.48 |
| 10 | adjacent2 | stop_exit | 270 | 33 | -676 | +1,249 | **+1,264** | +1,553 | 24.1% | -75.91 | -664.69 | -4,240 | 5 | 768 | -2,032 | 0.68 | 0.51 |
| 10 | adjacent2 | loss_exit | 266 | 37 | -659 | +1,264 | **+1,281** | +1,588 | 23.7% | -76.48 | -664.69 | -4,223 | 7 | 787 | -2,068 | 0.67 | 0.50 |
| 10 | adjacent2 | any_exit | 252 | 51 | -614 | +1,303 | **+1,326** | +1,705 | 22.2% | -77.99 | -664.69 | -4,083 | 14 | 982 | -2,308 | 0.65 | 0.48 |
| 10 | same_side_any | stop_exit | 270 | 33 | -676 | +1,249 | **+1,264** | +1,553 | 24.1% | -75.91 | -664.69 | -4,240 | 5 | 768 | -2,032 | 0.68 | 0.51 |
| 10 | same_side_any | loss_exit | 266 | 37 | -659 | +1,264 | **+1,281** | +1,588 | 23.7% | -76.48 | -664.69 | -4,223 | 7 | 787 | -2,068 | 0.67 | 0.50 |
| 10 | same_side_any | any_exit | 251 | 52 | -461 | +1,455 | **+1,479** | +1,863 | 22.3% | -77.61 | -664.69 | -4,083 | 14 | 982 | -2,461 | 0.58 | 0.43 |
| 10 | any_contract | stop_exit | 268 | 35 | -549 | +1,375 | **+1,391** | +1,683 | 24.3% | -76.04 | -664.69 | -4,113 | 5 | 768 | -2,159 | 0.62 | 0.46 |
| 10 | any_contract | loss_exit | 264 | 39 | -914 | +1,008 | **+1,026** | +1,338 | 23.5% | -76.34 | -664.69 | -4,478 | 8 | 1,148 | -2,174 | 0.84 | 0.62 |
| 10 | any_contract | any_exit | 247 | 56 | -575 | +1,339 | **+1,365** | +1,765 | 22.3% | -77.53 | -664.69 | -4,444 | 15 | 1,343 | -2,708 | 0.63 | 0.47 |
| 15 | same_symbol | stop_exit | 275 | 28 | -1,512 | +415 | **+428** | +700 | 22.5% | -77.17 | -664.69 | -4,820 | 8 | 729 | -1,157 | 1.43 | 1.22 |
| 15 | same_symbol | loss_exit | 271 | 32 | -1,495 | +430 | **+445** | +735 | 22.1% | -77.73 | -664.69 | -4,803 | 10 | 748 | -1,193 | 1.37 | 1.18 |
| 15 | same_symbol | any_exit | 263 | 40 | -1,506 | +416 | **+434** | +763 | 21.3% | -78.93 | -664.69 | -4,812 | 14 | 822 | -1,256 | 1.41 | 1.21 |
| 15 | adjacent1 | stop_exit | 260 | 43 | -867 | +1,052 | **+1,072** | +1,430 | 23.1% | -75.75 | -664.69 | -3,691 | 10 | 1,371 | -2,443 | 0.58 | 0.60 |
| 15 | adjacent1 | loss_exit | 258 | 45 | -849 | +1,070 | **+1,091** | +1,460 | 22.9% | -75.96 | -664.69 | -3,675 | 11 | 1,387 | -2,479 | 0.57 | 0.59 |
| 15 | adjacent1 | any_exit | 244 | 59 | -790 | +1,123 | **+1,150** | +1,586 | 21.7% | -77.88 | -664.69 | -3,507 | 17 | 1,569 | -2,719 | 0.54 | 0.56 |
| 15 | adjacent2 | stop_exit | 260 | 43 | -867 | +1,052 | **+1,072** | +1,430 | 23.1% | -75.75 | -664.69 | -3,691 | 10 | 1,371 | -2,443 | 0.58 | 0.60 |
| 15 | adjacent2 | loss_exit | 258 | 45 | -849 | +1,070 | **+1,091** | +1,460 | 22.9% | -75.96 | -664.69 | -3,675 | 11 | 1,387 | -2,479 | 0.57 | 0.59 |
| 15 | adjacent2 | any_exit | 243 | 60 | -799 | +1,114 | **+1,141** | +1,582 | 21.4% | -77.88 | -664.69 | -3,507 | 18 | 1,578 | -2,719 | 0.55 | 0.56 |
| 15 | same_side_any | stop_exit | 260 | 43 | -867 | +1,052 | **+1,072** | +1,430 | 23.1% | -75.75 | -664.69 | -3,691 | 10 | 1,371 | -2,443 | 0.58 | 0.60 |
| 15 | same_side_any | loss_exit | 258 | 45 | -849 | +1,070 | **+1,091** | +1,460 | 22.9% | -75.96 | -664.69 | -3,675 | 11 | 1,387 | -2,479 | 0.57 | 0.59 |
| 15 | same_side_any | any_exit | 242 | 61 | -646 | +1,266 | **+1,294** | +1,740 | 21.5% | -77.49 | -664.69 | -3,507 | 18 | 1,578 | -2,872 | 0.48 | 0.49 |
| 15 | any_contract | stop_exit | 256 | 47 | -712 | +1,206 | **+1,228** | +1,603 | 23.4% | -76.50 | -664.69 | -3,535 | 10 | 1,371 | -2,599 | 0.51 | 0.52 |
| 15 | any_contract | loss_exit | 255 | 48 | -713 | +1,204 | **+1,227** | +1,608 | 23.1% | -76.43 | -664.69 | -3,539 | 11 | 1,387 | -2,614 | 0.51 | 0.52 |
| 15 | any_contract | any_exit | 239 | 64 | -510 | +1,400 | **+1,429** | +1,888 | 21.8% | -78.00 | -664.69 | -3,449 | 18 | 1,578 | -3,007 | 0.44 | 0.45 |
| 30 | same_symbol | stop_exit | 265 | 38 | -1,644 | +278 | **+296** | +624 | 22.3% | -75.95 | -664.69 | -5,602 | 11 | 1,652 | -1,948 | 3.59 | 1.77 |
| 30 | same_symbol | loss_exit | 259 | 44 | -1,637 | +283 | **+303** | +657 | 21.6% | -76.90 | -664.69 | -5,594 | 14 | 1,681 | -1,984 | 3.50 | 1.73 |
| 30 | same_symbol | any_exit | 253 | 50 | -1,643 | +274 | **+297** | +680 | 20.9% | -77.73 | -664.69 | -5,599 | 17 | 1,750 | -2,047 | 3.58 | 1.76 |
| 30 | adjacent1 | stop_exit | 238 | 65 | -127 | +1,783 | **+1,813** | +2,284 | 23.9% | -74.51 | -664.69 | -4,203 | 13 | 2,294 | -4,107 | 0.59 | 0.35 |
| 30 | adjacent1 | loss_exit | 235 | 68 | -135 | +1,773 | **+1,805** | +2,288 | 23.4% | -74.83 | -664.69 | -4,196 | 15 | 2,320 | -4,125 | 0.59 | 0.35 |
| 30 | adjacent1 | any_exit | 223 | 80 | -199 | +1,704 | **+1,741** | +2,285 | 22.4% | -77.20 | -664.69 | -4,170 | 20 | 2,497 | -4,238 | 0.61 | 0.37 |
| 30 | adjacent2 | stop_exit | 238 | 65 | -127 | +1,783 | **+1,813** | +2,284 | 23.9% | -74.51 | -664.69 | -4,203 | 13 | 2,294 | -4,107 | 0.59 | 0.35 |
| 30 | adjacent2 | loss_exit | 235 | 68 | -135 | +1,773 | **+1,805** | +2,288 | 23.4% | -74.83 | -664.69 | -4,196 | 15 | 2,320 | -4,125 | 0.59 | 0.35 |
| 30 | adjacent2 | any_exit | 222 | 81 | -136 | +1,767 | **+1,804** | +2,355 | 22.1% | -76.78 | -664.69 | -4,139 | 21 | 2,506 | -4,310 | 0.59 | 0.35 |
| 30 | same_side_any | stop_exit | 238 | 65 | -127 | +1,783 | **+1,813** | +2,284 | 23.9% | -74.51 | -664.69 | -4,203 | 13 | 2,294 | -4,107 | 0.59 | 0.35 |
| 30 | same_side_any | loss_exit | 235 | 68 | -135 | +1,773 | **+1,805** | +2,288 | 23.4% | -74.83 | -664.69 | -4,196 | 15 | 2,320 | -4,125 | 0.59 | 0.35 |
| 30 | same_side_any | any_exit | 219 | 84 | 132 | +2,033 | **+2,072** | +2,642 | 22.4% | -76.57 | -664.69 | -4,139 | 21 | 2,506 | -4,578 | 0.51 | 0.31 |
| 30 | any_contract | stop_exit | 221 | 82 | 683 | +2,585 | **+2,622** | +3,164 | 24.0% | -75.27 | -664.69 | -3,439 | 17 | 2,327 | -4,949 | 0.41 | 0.24 |
| 30 | any_contract | loss_exit | 223 | 80 | 637 | +2,540 | **+2,577** | +3,115 | 23.3% | -74.12 | -664.69 | -3,459 | 18 | 2,343 | -4,920 | 0.41 | 0.25 |
| 30 | any_contract | any_exit | 209 | 94 | 794 | +2,691 | **+2,734** | +3,353 | 22.5% | -75.45 | -664.69 | -3,464 | 23 | 2,636 | -5,371 | 0.39 | 0.23 |

❌ = cell **loses** money versus production. Δ net+slip adds the measured one-sided exit optimism (0.129 of the exit minute's traded range, [COST-REALISM-2026-08-18](COST-REALISM-2026-08-18.md)); it is larger than Δ net because a blocked trade also never pays that slippage. Slippage range imputed from the book median ($0.085) on 5 of 303 rows where the exit-minute bar had no usable range; those rows are flagged, not dropped.

**Negative top-day / top-trade shares mean the single largest contributor to that cell's delta was a blocked WINNER — the rule's biggest single action made the book worse.**

---

## 4. Why the best-looking cell is rejected

`30 min · any contract · after any exit` is the top of the matrix at **+$2,734 net**. It fails three independent checks.

### 4a. It eats the right tail

| date | arm | entry | contract | net | blocked because | its own exit |
|---|---|---|---|---:|---|---|
| 2026-08-04 | risky-1 | 09:50:07 | `SPY260804C00763000` | **$639.53** | 3.0 min after `SPY260804C00762000` exited | tp1 |
| 2026-08-04 | risky-3 | 09:57:09 | `SPY260804C00763000` | **$523.29** | 10.0 min after `SPY260804C00762000` exited | tp1 |
| 2026-08-10 | risky-3 | 09:58:08 | `SPY260810C00775000` | **$361.14** | 18.0 min after `SPY260810C00775000` exited | tp1 |
| 2026-08-11 | bold-2 | 14:07:47 | `SPY260811P00771000` | **$296.54** | 21.7 min after `SPY260811P00771000` exited | tp1 |
| 2026-08-11 | risky-1 | 14:08:08 | `SPY260811P00771000` | **$265.54** | 21.0 min after `SPY260811P00771000` exited | tp1 |
| 2026-08-12 | risky-1 | 14:17:09 | `SPY260812C00773000` | **$121.55** | 21.0 min after `SPY260812P00773000` exited | tp1 |
| 2026-07-17 | safe-2 | 14:03:18 | `SPY260717P00745000` | **$104.72** | 0.3 min after `SPY260717P00746000` exited | tp1 |
| 2026-08-11 | risky-3 | 09:51:09 | `SPY260811P00771000` | **$55.32** | 4.0 min after `SPY260811P00771000` exited | ribbon_flip |

- **23 winners destroyed, $2,636.32** — **16.8% of the $15,654 of winner dollars this book has ever produced.**
- The largest is **$639.53** — the **#4 single winner in the whole dataset**. **7 of the 23 destroyed winners exited at `tp1`**: these are not lucky scratches, they are the trades that hit target.
- The top 5 winners carry 22.5% of all winner dollars in this book. A rule whose single biggest action is deleting a top-5 trade is not a loss-control rule. **It is the same trap as a tight stop, wearing a different hat.**

### 4b. Three days are the whole effect

| day | Δ from blocking | cumulative share |
|---|---:|---:|
| 2026-08-05 | +1,063 | 38.9% |
| 2026-08-07 | +830 | 69.2% |
| 2026-08-12 | +530 | 88.6% |
| 2026-07-02 | +323 | 100.4% |
| 2026-08-10 | +229 | 108.8% |
| … 14 more days … | | |
| 2026-08-04 | **-509** | (rule LOSES money) |
| 2026-08-11 | **-576** | (rule LOSES money) |

- **Top day = 38.9%. Top 3 days = 88.6%.**
- Rule 3 of this lane's own honesty rules: *an edge carried by 2 days is not an edge.* This one is carried by 3.

### 4c. It barely beats "just trade less"

Control: remove the **same number of trades, at random, stratified by arm**, 4,000 draws. Because the book is net negative, deleting trades at random is *expected* to help.

| cell | Δ net | random-removal mean | p(random ≥ rule) |
|---|---:|---:|---:|
| 30 min · any_contract · any_exit | +2,734 | +558 | 0.067 |
| 30 min · any_contract · stop_exit | +2,622 | +500 | 0.056 |
| 10 min · same_side_any · any_exit | +1,479 | +328 | 0.154 |
| 3 min · same_symbol · stop_exit | +1,031 | +108 | 0.051 |

**And the volume story runs the wrong way anyway:**

| day type | days | net |
|---|---:|---:|
| ≥12 round trips (busy) | 11 | **$258** |
| <12 round trips (quiet) | 24 | **$-2,198** |

The busy days are the *profitable* days. Any blanket throttle is fighting the wrong variable.

### 4d. The surface is knife-edged, not smooth

`any contract · any exit`, sweeping only the cooldown:

| cooldown | blocked | Δ net | winners killed | biggest winner killed |
|---:|---:|---:|---:|---|
| 0 min | 0 | +0 | 0 | — |
| 3 min | 32 | +1,350 | 10 | 2026-07-17 safe-2 $105 |
| 5 min | 43 | +64 | 15 | 2026-08-04 risky-1 $640 |
| 10 min | 56 | +1,365 | 15 | 2026-08-04 risky-1 $640 |
| 15 min | 64 | +1,429 | 18 | 2026-08-04 risky-1 $640 |
| 30 min | 94 | +2,734 | 23 | 2026-08-04 risky-1 $640 |

**+$1,350 at 3 min → +$64 at 5 min → +$1,365 at 10 min.** The collapse at 5 minutes is *one trade*: 2026-08-04 risky-1 +$639.53 entered exactly 3.0 minutes after the prior exit, so it survives a 3-minute rule and dies under a 5-minute one. **A parameter surface where one trade flips the sign is noise, not an edge.**

---

## 5. What survives — the recommended cell

### `3 minutes · SAME SYMBOL · only after a premium/structure STOP`

| metric | production ⬛ | with cooldown | Δ |
|---|---:|---:|---:|
| round trips | 303 | 288 | −15 |
| **gross P&L** | $-1,805 | $-781 | **+1,024** |
| **net of real fees** | $-1,940 | $-909 | **+1,031** |
| **net of fees + exit slippage** | $-3,814 | $-2,639 | **+1,175** |
| win rate | 23.1% | 23.3% | +0.2 pp |
| avg loss | $-75.51 | $-74.51 | +1.00 |
| worst loss | $-664.69 | $-664.69 | unchanged |
| max drawdown | $-5,263 | $-4,712 | **+551** |
| winner dollars destroyed | — | $96.80 | **0.62% of all winner dollars** |

**Win rate up AND net up AND drawdown smaller — this cell is not the WR-up/net-down failure mode.** It is also the only cell in the matrix that touches the right tail almost not at all.

Every trade it blocks, in full — 15 rows, nothing hidden:

| date | arm | entry | contract | gap after the stop | net | prior exit was | setup |
|---|---|---|---|---:|---:|---|---|
| 2026-07-02 | safe-2 | 09:57:15 | `SPY260702C00750000` | 0.2 min | $-76.28 | premium_stop | vwap_continuation |
| 2026-07-02 | safe-2 | 10:22:27 | `SPY260702C00751000` | 0.4 min | $-21.28 | premium_stop | vwap_continuation |
| 2026-07-06 | safe-2 | 13:13:40 | `SPY260706C00751000` | 0.2 min | $-21.28 | premium_stop | bollinger_squeeze |
| 2026-07-16 | safe-2 | 09:53:45 | `SPY260716P00751000` | 0.7 min | $-14.28 | premium_stop | vwap_continuation |
| 2026-07-20 | safe-2 | 09:54:19 | `SPY260720C00748000` | 2.3 min | $-18.28 | premium_stop | vix_regime_dayside |
| 2026-07-21 | safe-2 | 10:12:28 | `SPY260721P00745000` | 0.4 min | **$17.72** | premium_stop | vwap_reclaim_failed_break |
| 2026-07-22 | safe-2 | 10:10:41 | `SPY260722C00749000` | 0.6 min | $-45.28 | premium_stop | vwap_continuation |
| 2026-08-04 | risky-3 | 09:54:07 | `SPY260804C00763000` | 2.0 min | $-144.70 | premium_stop | VWAP_CONTINUATION |
| 2026-08-05 | risky-1 | 10:10:06 | `SPY260805C00776000` | 2.0 min | $-100.47 | premium_stop | VWAP_CONTINUATION |
| 2026-08-05 | risky-3 | 10:10:07 | `SPY260805C00776000` | 1.0 min | $-160.71 | premium_stop | VWAP_CONTINUATION |
| 2026-08-05 | risky-1 | 10:18:06 | `SPY260805C00776000` | 1.0 min | $-155.46 | premium_stop | VWAP_CONTINUATION |
| 2026-08-05 | risky-3 | 10:18:07 | `SPY260805C00776000` | 1.0 min | $-296.70 | premium_stop | VWAP_CONTINUATION |
| 2026-08-11 | risky-1 | 09:55:07 | `SPY260811P00773000` | 2.0 min | **$39.54** | premium_stop | VWAP_CONTINUATION |
| 2026-08-12 | risky-1 | 09:52:07 | `SPY260812P00773000` | 3.0 min | **$39.54** | premium_stop | VWAP_CONTINUATION |
| 2026-08-17 | risky-3 | 09:56:08 | `SPY260817P00776000` | 1.0 min | $-72.69 | premium_stop | VWAP_RECLAIM_FAILED_BREAK |

| day | Δ | share |
|---|---:|---:|
| 2026-08-05 | +713.34 | +69.2% |
| 2026-08-04 | +144.70 | +14.0% |
| 2026-07-02 | +97.56 | +9.5% |
| 2026-08-17 | +72.69 | +7.1% |
| 2026-07-22 | +45.28 | +4.4% |
| 2026-07-06 | +21.28 | +2.1% |
| 2026-07-20 | +18.28 | +1.8% |
| 2026-07-16 | +14.28 | +1.4% |
| 2026-07-21 | -17.72 | -1.7% |
| 2026-08-11 | -39.54 | -3.8% |
| 2026-08-12 | -39.54 | -3.8% |

- **Top day 2026-08-05 = 69.2% of the whole effect.** That day is a genuine spiral: risky-1 and risky-3 each bought `SPY260805C00776000` **five times** between 09:58 and 10:18 — 10 round trips on one contract in 20 minutes, **every single one stopped out**, $-1,284.88 combined.
- ⚠️ **And the recommended rule only catches 4 of those 10 legs ($713 of $1,285).** The other legs paced themselves 5–6 minutes apart and walk straight through a 3-minute gate. **The rule is not a cure for the spiral; it clips the fastest legs off it.**
- **Top single blocked trade = 28.8%** of the effect.
- The day's actual worst trade — risky-3 −$664.69, the largest single loss in the book — was entered at 11:48 with hours of gap behind it. **No cooldown in this matrix touches it.** Churn is not where the biggest losses come from.
- 3 of the 15 blocked trades were winners, worth $96.80 combined. The rule pays for them ten times over — but they are the honest cost and they are stated here, not netted away.

### Robustness of that cell

| subset | trips | blocked | Δ net | random-removal mean | p | top-day share |
|---|---:|---:|---:|---:|---:|---:|
| FULL (all 35 days) | 303 | 15 | **+1,031** | +108 | 0.051 | 69% |
| drop the 3 best days | 239 | 10 | **+357** | -80 | 0.178 | 41% |
| first half (< 2026-07-27) | 117 | 7 | **+179** | +149 | 0.493 | 55% |
| second half (≥ 2026-07-27) | 186 | 8 | **+852** | -6 | 0.079 | 84% |

- **Sign-stable in all four subsets** — the only cell in the matrix that is both sign-stable and right-tail-safe.
- But **p = 0.051 on the full sample and 0.493 in the first half.** The first half of the dataset contains no evidence for this rule at all; the second half contains it, concentrated in one day.

---

## 6. Independence — what n really is

- 303 round trips, but the 5 arms trade **one shared signal** (r=0.846, 95.7% sign agreement). The matrix-builder's own warning applies: never quote 303 as a sample size.
- The recommended cell makes **15 blocking decisions across 11 distinct days and 13 five-minute signal clusters**. Within a cluster the arms are copies of each other, not independent observations.
- **Conservative n_effective = 11** (distinct days). Nine of those eleven days contribute under $100 each.
- The 30-minute cell's n_effective is 21 days — larger, but 3 of them are 89% of the money, so its *effective* n for the dollars that matter is closer to 3.

---

## 7. The 38-of-101 question: NOT a logging gap

Joined all 101 safe-2/bold-2 round trips on the **broker order id of the buy leg** against `automation/state/core-decisions.jsonl`:

| where the PLACED row lives | trips |
|---|---:|
| top-level `action: "PLACED"` | **63** |
| inside `extra_exec[].action: "PLACED"` (watcher lane) | **38** |
| no order id anywhere in the ledger | **0** |

**Answer: it is an unlogged-*looking* second entry path, not a logging gap. Nothing is missing.** The core ribbon engine writes `action: "PLACED"` at the top level of its decision row. The **extra-signal / watcher lane** (`bollinger_squeeze`, `vwap_continuation`, `vwap_reclaim_failed_break`, `vix_regime_dayside`) places its own orders and logs them in an `extra_exec[]` array *inside a row whose top-level verdict is usually `HOLD`* — the core setup said no, the watcher fired anyway. Any join filtering on top-level `action == "PLACED"` sees 63 and concludes 38 are missing. All 101 are accounted for.

**And the second path is the worse half of the book:**

| entry path | trips | net | win rate |
|---|---:|---:|---:|
| core ribbon (top-level PLACED) | 63 | $-415.36 | 27.0% |
| **watcher lane (`extra_exec`)** | 38 | **$-870.64** | **18.4%** |

This matters for *this* lane specifically: **the churn is entirely a watcher-lane phenomenon.** **All 15 of the 15 trades the recommended cooldown blocks come from watcher setups — not one from the core ribbon path.** The core path re-enters far less aggressively and already carries one-position-at-a-time discipline.
- **The existing same-bar guard does not cover this.** 11 of the 15 blocked trades happened **on or after 2026-07-20**, when `same_bar_cooldown_active` was already live. It keys on the *trigger bar*, so a stop-out followed by a genuinely new trigger bar re-arms the setup immediately — which is exactly the 1–2 minute pattern in the table above. **A same-symbol time gate is a different mechanism, not a duplicate of the shipped guard.**

---

## 8. Two scars, re-measured

**2026-08-17 — confirmed, and small.** risky-3 was stopped out of `SPY260817P00776000` at 09:55:08 (−$64.69) and bought the identical contract back at 09:56:08 — a **1.0-minute** gap — for another −$72.69. Combined −$137.38, matching the −$136 in the brief. The recommended cell blocks exactly the second leg. The day's actual money was elsewhere: bold-2 `tp1` +$359.54 at 13:06, untouched by any cooldown in the matrix.

**2026-08-12 — bigger than the brief said, and the cooldown does not clean it up.** The day is 38 round trips, net **$-908.01** (the −$574 / 64.5% figure in the brief is a narrower slice). Between 09:46 and 10:06 the five arms put on **21 round trips with 3 direction flips**, for **$-818.64**. But the day's two best trades — risky-1 `tp1` +$121.55 and safe-3 +$44.72, both entered 14:17 — sit **21 minutes** after the prior exit and are **destroyed by the 30-minute cooldown**. The 3-minute same-symbol rule blocks two trades that day and nets **−$39.54** (it blocks a *winner*). Even on the canonical churn day, the tight rule is a small loss and the wide rule buys its gain by deleting the recovery.

---

## 9. Pre-registered hypothesis — SHADOW ONLY

> **Not a fix. Nothing is armed by this document.** Per OP-11 this ships as a shadow pre-registration with a kill criterion fixed in advance.

**H-CHURN-1.** *A 3-minute cooldown on re-entering the SAME option symbol after a premium or structure stop, scoped per arm, improves net P&L without material right-tail damage.*

- **Rule:** on a `premium_stop` or `structure_stop` exit of symbol S on arm A, refuse any new entry in symbol S on arm A for 180 seconds. Different strike, different side, different arm: unaffected. No effect on exits, ever.
- **Decidable with no look-ahead:** the only inputs are the prior exit's timestamp, its reason, and its symbol.
- **Prior (this document, in-sample):** +$1,024 gross / +$1,031 net / +$1,175 after exit slippage over 35 days; 15 blocks; 3 blocked winners worth $96.80.
- **Shadow-log only** — write what it *would* have blocked, change nothing.

### Kill criterion (fixed now, in advance)

**Kill H-CHURN-1 if, after 20 further blocking events or 60 trading days (whichever comes first), ANY of:**

1. cumulative net of the shadow-blocked set is **> −$150** (the blocked trades were not meaningfully losers — the rule is blocking noise);
2. **any single blocked trade is a winner larger than +$250** (one right-tail kill wipes out the whole in-sample edge);
3. the **top single day carries > 50%** of the shadow-period delta (concentration reproduces rather than resolves);
4. shadow-period Δ net is **negative**.

**Graduate only if** shadow Δ net > +$300 with top-day share < 50% AND blocked-winner dollars < 2% of period winner dollars.

### Explicitly NOT proposed

- **Any cooldown ≥ 5 minutes**, and **any cooldown scoped wider than the same symbol.** They score higher in-sample and they are the trap: they buy their number by deleting `tp1` winners, including a **top-5 trade** ($639.53, rank #4 in the book).
- **Any per-day trade throttle.** The busy days are the profitable days (≥12 trips: $258; <12 trips: $-2,198).

---

## 10. What this lane did NOT find

- **No cooldown makes this book profitable.** The best robust cell moves it from −$1,940 to −$909 net; after exit slippage, from −$3,814 to −$2,639. Still a losing book.
- **Concurrency is a non-issue.** Only 2 of 303 entries opened while another position was already live on the same arm (net −$16.73), and **zero** were same-symbol adds. The one-position-at-a-time discipline is holding; the churn is strictly *sequential* re-entry, not averaging down.
- **The 30-minute result is not fabricated — it is real and it is a trap.** +$2,734 is what the arithmetic says. It is rejected on mechanism, not on arithmetic.

---

*Generated by `setup/scripts/`-adjacent scratch analysis on the canonical trade matrix; every figure above is computed at build time, none transcribed by hand. Costs: fees per `cost_model.py` (`fee_total_ex_cat`), exit slippage per `exit_fill_realism.py` (0.129 of exit-minute range). Analysis only — arms nothing.*
