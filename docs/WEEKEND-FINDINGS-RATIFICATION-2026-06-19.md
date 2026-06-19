# Weekend Findings — Ratification Package (2026-06-19)

> Output of the autonomous weekend research loop. Everything below is **propose-only (Rule 9)** — validated on real-fills + OOS, ready for J / the conductor to ratify (or revoke). The honest caveat on ALL of it: real-fills used historical ★★ proxy levels (no ★★★ archive over the window) + OPRA ends ~2026-05-29 — so these are evidence-strong-but-proxy-bounded; the just-fixed ★★★ archive will let them be re-confirmed on real levels going forward.

## ✅ READY TO RATIFY (OOS-validated propose-candidates)

| # | Change | Evidence | Blocker before ship |
|---|---|---|---|
| **1** | **Chandelier trail 20% → 15%** (Safe, premium profit-lock) | OOS same-sign EVERY split + **6/6 walk-forward folds**; broad-based (18 trades improved / 0 worse — Pareto, not fat-tail); ATM +$1.4k, ITM2 sign-flips positive; a co-leader inverted OOS (discipline has teeth). Scorecard: `analysis/recommendations/regime-chandelier-sweep.json` | Anchor coverage: 5/01 & 5/04 ungradeable on proxies → anchor-no-regression untested for J's 2 biggest winners. Confirm on real ★★★ levels first. |
| **2** | **Confidence tier: STOP sizing up on HIGH** (bearish_rejection) + adopt corrected VIX-character tier (Safe/ATM) | CONFIRMED inversion (sizes up on worst trades); OLD loses ~$700 > flat; corrected tier +$3.2k vs flat, OOS sign-stable on ATM. Min fix (cap HIGH ≤1.0x) is robust on both strikes. Scorecard: `bearish-rejection-tier-recalibration.json` | None for the min fix (cap HIGH) — it's a pure safety win. Full corrected tier: ATM only (ITM2 size-up leg flips, C29). |
| **3** | **VIX-falling = SKIP** for BEARISH_REJECTION | Sign-stable negative both OOS halves (−$189/27%WR); clean mirror of the proven VIX-rising gate. Scorecard: `bearish-rejection-quality-validation.json` | None (do-no-harm). Low-n (11) → propose as skip, not a sized rule. |

**Recommended ratification order:** #2-min (cap HIGH, zero-risk safety fix) → #3 (VIX-falling skip, do-no-harm) → #1 (trail 15%, after real-level anchor check). All are Safe-account; Bold/ITM2 takes only the conservative halves (C29 — knobs don't transfer across strike tiers).

## ❌ CONCLUSIVELY RULED OUT (don't spend more effort)

- **Mean-reversion bounce family** (floor_hold, close_ceiling, named_level_second_test) — dead/anti-edge under every exit/regime/short-inversion tested.
- **New bearish-continuation entries** (trendline/TBR, momentum, VWAP-rejection) — all anti-edge or no-coverage; TBR *actively* anti-edge. **BEARISH_REJECTION is the only edge-aligned entry, period.**
- **Morning-sign / intraday-momentum gate** — look-ahead mirage; inverts OOS (L166).
- **Lunch-trough / time-of-day gate** — no-win; our bleed is the 10:00 morning shoulder, not lunch (L167).
- **Theta-cliff earlier time-stop** — no-win; the confirmed setup resolves by midday (C28).
- **Vol-scaled (wider-in-high-vol) chandelier** — inverts for 0DTE (theta dominates → catch winners faster, hence #1).

## 🔧 BUILT / UNBLOCKED (infrastructure, going-forward)

- **★★★ key-levels archive** — the #1 data constraint. Added a $0 safety-net archiver to the backtest-consumed path; today snapshotted; proved real Carry-tier levels now feed validation. **Once ~20-30 real trading days bank, re-run all level-keyed validations on real levels** — the proxy RETIRE verdicts (and #1's anchor check) may change.
- **GEX regime tag** (`backtest/lib/engine/gex_regime.py`) — net dealer-gamma sign/flip/walls computed $0 from our option chain. Tested; can't backtest (no historical chain OI) → live going-forward regime tag. The one peer-reviewed regime signal worth wiring once data banks.
- **Lessons L166/L167** graduated to LESSONS-LEARNED + OP-25.

## THE STANDING TRUTH (what the whole weekend confirmed)

1. **BEARISH_REJECTION is the edge** — the only entry that fires with J's bearish-continuation winners. Stop hunting new entries.
2. **The leverage is exit/regime refinement of that one setup** — and the wins above (#1 trail, #2 tier, #3 VIX-skip) are exactly that.
3. **The proxy-data wall is the ceiling** — the setup is real-fills-negative on proxy levels, but J's real winners were on real ★★★ levels the proxies miss. Resolving this (the archive, now accruing) is the single highest-value thing for confirming our true edge. **The real validation resumes with Monday's live data + the accumulating archive.**
