# WP-5 — `vwap_continuation` STRIKE A/B SCORECARD

**The live-edge OTM-2 mis-strike leak — decision-grade A/B on real OPRA fills.**

> **Verdict (one line):** The ONE live edge (`vwap_continuation`, `j_vwap_cont_enabled=true` on Safe-2) is running at **OTM-2**, the WEAKEST of four strike cells. OTM-2 is a *positive* edge but the **leak vs the validated ATM cell is +$29.78/tr OOS (~$3,431/yr)**, and vs the Bold-validated ITM-2 cell **+$64.59/tr OOS (~$7,441/yr)**. Strike gradient is monotonic **ITM > ATM > OTM** and every cell clears the 11-gate bar — so this is a clean re-strike, not a stop/null artifact. **Recommended live strike: Safe-2 → ATM, Bold → ITM-2 (per-setup, C29).** DECISION-GRADE for J.

- **Run:** `backtest/autoresearch/_wp5_strike_ab.py` (RESEARCH-only; no live file touched)
- **Output JSON:** `analysis/recommendations/wp5-strike-ab.json`
- **Run date:** 2026-06-21 · **Window:** 2025-01-01 .. 2026-05-29 (hard-windowed to OPRA cache edge)
- **Fills authority:** real OPRA via `lib.simulator_real.simulate_trade_real` (C1)
- **Detector:** VALIDATED `_edgehunt_vwap_continuation.detect_signals` — byte-for-byte the live `vwap_continuation_watcher` port. Signals detected **ONCE** (166 signals on 166 days, 45.7% of 363 trading days, side C:90/P:76, ~115.2 signals/yr) then re-simulated at each strike; **only the strike offset varies.**
- **Held constant across all cells:** premium_stop_pct = −0.08 (v15 tight stop), qty=3, v15 exits, snap radius ≤4.
- **C7 assert (passed):** `last_fill_date_overall = 2026-05-29 == cache_edge` → no past-cache fill bleed.

---

## Strike-offset convention crosswalk (load-bearing — sim-accuracy gate, OP-16)

Two INVERSE conventions exist; mis-stating this invalidated a whole weekend once.

| | OTM-2 | ATM | ITM-1 | ITM-2 |
|---|---|---|---|---|
| **simulator_real** (puts strike=atm−off, calls=atm+off; L357-364 → NEG=ITM) | `+2` | `0` | `-1` | `-2` |
| **live params** `v15_strike_offset_per_tier` (NEG=OTM, INVERSE) | `-2` | `0` | `+1` | `+2` |

The live **Safe-2 ($2K)** tier is `v15_strike_offset_per_tier[2000..10000] = -2 = "OTM-2"` (confirmed end-to-end in B1's smoke test: Safe-2 heartbeat strike = OTM-2). So the live cell = **sim +2**.

---

## The A/B (real OPRA, n per cell, IS=2025 / OOS=2026)

| cell | role | n | WR % | full $/tr | IS $/tr | OOS $/tr | pos Q | top5-day % | drop-top5 $/tr | **OOS-drop-top5 $/tr** | null max | no-trunc | **clears 11-gate** |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:--:|:--:|
| **OTM-2** | **LIVE Safe-2** | 151 | 39.7 | **+15.67** | +15.35 | **+16.45** | **4/6** | 63.7 | +5.89 | **+1.17** | 6.08 | ✅ | ✅ |
| **ATM** | **validated Safe-2** | 153 | 48.4 | +40.05 | +37.39 | **+46.23** | 6/6 | 33.3 | +27.61 | +15.44 | 6.89 | ✅ | ✅ |
| ITM-1 | intermediate | 153 | 46.4 | +45.09 | +38.96 | +59.37 | 6/6 | 31.1 | +32.12 | +22.99 | 14.24 | ✅ | ✅ |
| **ITM-2** | **validated Bold** | 153 | 47.1 | **+65.31** | +58.55 | **+81.04** | 6/6 | 24.1 | +51.25 | +38.22 | 10.39 | ✅ | ✅ |

**Monotonic gradient ITM > ITM-1 > ATM > OTM** in every robustness column (full, OOS, drop-top5, OOS-drop-top5). Every cell beats its 20-seed random-entry null (chosen >> null_max) and shows NO truncation artifact (chart-stop-only ≥ chosen at every cell), so the edge is a genuine option edge that strengthens as you move ITM — **not** a stop-truncation or exit-bracket artifact.

---

## THE LEAK (cost of running the live edge at OTM-2)

Annualized = leak/tr × **115.2 signals/yr** (45.7% fire-day rate × 252).

| comparison | full-sample $/tr | full-sample $/yr | **OOS $/tr** | **OOS $/yr** |
|---|---:|---:|---:|---:|
| **ATM − OTM-2** (Safe-2 mis-strike) | **+24.38** | ~$2,809 | **+29.78** | **~$3,431** |
| ITM-1 − OTM-2 | +29.42 | ~$3,389 | +42.92 | ~$4,944 |
| **ITM-2 − OTM-2** (Bold validated vs live tier) | **+49.64** | ~$5,719 | **+64.59** | **~$7,441** |

---

## Is OTM-2 (the live strike) actually a positive edge?

**Yes — but it is the WEAKEST cell and its edge is fragile.**
- OTM-2 is positive on every aggregate (full +$15.67, IS +$15.35, OOS +$16.45) and *technically* clears the 11-gate bar.
- BUT its quality is visibly degraded vs every richer strike:
  - **posQ only 4/6** (vs 6/6 for ATM/ITM-1/ITM-2) — two losing quarters.
  - **WR 39.7%** (vs 46-48%) — the classic OTM **theta/delta drag** (C3/C29): right direction, but the cheap far-OTM contract decays before the move pays.
  - **OOS-drop-top5 = +$1.17/tr** — almost the entire OTM-2 OOS edge is carried by a handful of days; remove the 5 best and it's barely above zero. ATM's is +$15.44, ITM-2's +$38.22 — robustly positive.
  - **top5-day concentration 63.7%** (vs 24-33% for richer strikes).

So OTM-2 is "positive on paper, fragile in practice." The richer strikes are **decisively better:** ATM beats it by +$29.78/tr OOS and is robust (posQ 6/6, OOS-drop-top5 +$15.44); ITM-2 beats it by +$64.59/tr OOS.

---

## Verdict & recommended live strike (per-setup, C29)

| account | current LIVE | **recommended** | OOS lift over live | annualized lift |
|---|---|---|---:|---:|
| **Safe-2** ($2K) | OTM-2 | **ATM** | **+$29.78/tr** | **~$3,431/yr** |
| **Bold** | OTM-2* | **ITM-2** | **+$64.59/tr** | **~$7,441/yr** |

\* Bold's `j_vwap_cont_enabled` key is currently absent → the edge is INERT on Bold (B1 finding #1). When wired, it should run at ITM-2, not OTM-2.

**This is the per-setup C29 fix:** `vwap_continuation` → its validated strike per account. It is **NOT** a blanket v15-tier change — strikes ratified on one setup/tier do not transfer to another, and the generic v15 OTM-2 tier stays correct for every OTHER setup on Safe-2.

**L174 concentration caveat does NOT apply here:** that caveat is about *adding* edges #2/#4 (which are same-side re-cuts of #1). WP-5 re-strikes the EXISTING live edge — no new concentration, no independence assumption.

**Bull-tape caveat:** OOS = 2026 (bull regime). The absolute OOS numbers are bull-flattered, but the A/B is **bias-cancelled** (same tape across all four cells) and the gradient is mirrored IS↔OOS, so the *relative* leak is robust even if absolute magnitudes compress in chop/bear.

---

## Decision-grade for J?

**YES.** 8-of-8-style gates clear on the validated cells (n≥20, OOS>0, IS>0, full>0, posQ 6/6, top5<200%, drop-top5>0, OOS-drop-top5>0, beats-null, no-truncation); the leak is large, monotonic, and bias-cancelled; the fix is a single per-setup flag in daylight (build-spec below). Per OP-22 / FORBIDDEN-FRAMING this is a profitable, validated improvement to an **already-live** edge — it ships under the standing authorization with a REVOKE note, it is NOT a "want me to flip it?" gate.

> **Why WP-5 is MORE URGENT than WP-0's dormant edges:** WP-0 unlocks edges #2/#4 that are NOT yet trading. WP-5 fixes the strike on the edge that is **trading real (paper) capital RIGHT NOW** at the weakest cell — every live `vwap_continuation` fill at OTM-2 leaves ~$30/tr (Safe) on the table vs its validated ATM cell.
