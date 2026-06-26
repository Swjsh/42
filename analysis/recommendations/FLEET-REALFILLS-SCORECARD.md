# WATCH_ONLY Fleet — Consolidated Real-Fills Scorecard — 2026-06-20

> Cook deliverable (J: "backtest it to infinity… don't leave anything untested"). Every watcher with a real-fills validator, scored on **real OPRA fills** (C1) for **per-trade EXPECTANCY** (OP-14, not WR), against the OP-11 bar: per-trade>0 AND OOS>0 AND positive_quarters≥4/6 AND top5<200% AND n≥20.
> Sources: `EDGE-HUNT-VERIFIED.json` (9 families, full OOS/quarter/concentration), this cook's `double-top-real-fills.json` + refreshed `db-morning`, and the legacy `*_real_fills_*.json` artifacts. Machine board: `fleet-realfills-scorecard.json`. Pure-Python, $0, no agents (throttle-proof).

## Verdict in one line
**Of ~16 watchers, exactly ONE clears the bar — `vwap_continuation`, which is already LIVE. Everything else is awareness-grade or dead on real fills. Nothing new is promotable.**

## The board

| Watcher | n | $/trade | OOS $/t | pos-Q | top5% | Verdict |
|---|---|---|---|---|---|---|
| **vwap_continuation** (LIVE) | 149 | $46→**$78** (ITM-2) | **+$105** | **6/6** | 21% | ✅ **CLEARS OP-11** (the edge; already live) |
| double_bottom_base_quiet | 122 | +$14 | +$26 | 4/6 | 167% | 🟡 AWARENESS — borderline (OOS-conc 249%); calls-only |
| double_bottom_morning | 109 | +$8 | — | — | — | 🟡 AWARENESS — modest +, OOS/Q unverified |
| hs_bear | 19 | +$18 | — | — | — | 🟡 AWARENESS — too thin (n<20) |
| fbw_morning_mid | 35 | +$13 | — | — | — | 🟡 AWARENESS — WF unstable (train −$444 / test +$899) |
| orb_retest | 57 | +$9–13 (OTM+tuned) | +$13 | 5/6 | 103% | 🟡 AWARENESS — exit-tuned + thin OOS (~17) |
| lbfs / v14e_ampm / orb_narrow | 12–19 | — | — | — | — | 🟡 INSUFFICIENT-N (≤19) |
| **double_top** | 354 | **−$48** | −$51 | **0/6** | — | ❌ DEAD (theta trap: 54% WR, neg EV) |
| **confluence / market_structure** | 1047 | **−$22** | — | **0/6** | — | ❌ DEAD (the killed signal; do NOT promote market_structure_watcher) |
| **nlwb** | 23 | **−$56** | — | — | — | ❌ DEAD |
| **bull_ribbon_reversal** | — | **−$245 tot / 0 wins** | — | — | — | ❌ DEAD |
| **momentum_accel** (default) | 35 | **−$21** | — | — | — | ❌ DEAD at default exits (only +$82 with chandelier+OTM — exit-dependent, n=35, NOT ratify-ready) |
| **bearish_rejection_morning** | 122 | −$14 (ITM2) | −$8 | — | 231% | ❌ DEAD for promotion — also FAILS OP-16 anchor gate (edge_capture −44) |
| **v14_enhanced** (authorized bear) | 96 | ~$0 bear | — | — | — | ❌ no authorized edge — aggregate only clears via the *unauthorized* bull book (C4/C24) |

## What this means (honest)
1. **The fleet is mostly awareness/dead on real option fills.** A high SPY-shape win-rate ≠ option edge — `double_top` (54% WR, −$48/trade) and `confluence` (60% WR, −$22/trade) are the textbook theta traps (C3/L58/OP-14).
2. **No new watcher is ratify-ready.** The marginal positives (double_bottom ×2, hs_bear, fbw, orb) are either thin-N, OOS-unverified, WF-unstable, or concentration-borderline — leads, not edges. Per anti-pattern 2.10, none get promoted on this evidence.
3. **The two new structure watchers are DEAD on real fills:** `double_top` (−$48/trade, 0/6Q) and `market_structure`(=confluence, −$22/trade, 0/6Q). **Do NOT promote either to a live trigger.** They stay WATCH_ONLY / awareness telemetry.
4. **The one real edge (`vwap_continuation`) is already live at ITM-2 + −8%** — the optimal config the edge-hunt independently found. We're capturing it.

## Promotion recommendations
- **Promote:** nothing new (vwap already live).
- **Keep WATCH_ONLY, gather N before re-test:** double_bottom (base+morning), hs_bear, orb, fbw.
- **Stop pursuing as triggers (real fills say no):** double_top, market_structure/confluence, nlwb, bull_ribbon, momentum (default), bearish_rejection (anchor-fail), v14 authorized-bear.

*Cook complete. Nothing left untested — every watcher with a validator is scored above.*
