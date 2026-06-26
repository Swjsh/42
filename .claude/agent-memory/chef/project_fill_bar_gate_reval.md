---
name: project-fill-bar-gate-reval
description: require_bearish_fill_bar re-validated UNBLOCK under current engine — gate now suppresses net-winning bear trades because managed ITM exits inverted its old bracket-only economics
metadata:
  type: project
---

# require_bearish_fill_bar (gates.py #7) — RE-VALIDATED 2026-06-26 → UNBLOCK-leaning

**The gate is a BEAR/P block, NOT a bull block.** Work item mislabeled it "bull-direction block." It fires only on `side=="P"`: look-ahead gate that skips a bear entry when the fill bar N+1 closes bullish/doji. Bold=true (J-ratified 2026-06-17, AUTO-RATIFY on the sweep). Safe=REJECT (anchor FAIL on old engine).

**Why it's now stale:** ratified on the OLD bracket-only OTM profile (TP1 + fixed runner_target + premium_stop, no chandelier). Under the CURRENT Bold engine (real fills, `strike_offset=-2` ITM-2, `premium_stop_pct_bear=-0.07`, chandelier `profit_lock_mode=trailing` arm +5% / trail 15%) the economics INVERTED.

**Evidence (the decisive bit):** the *removed-trade audit* is the clean test — run gate OFF vs ON, find the bear trades present in OFF/absent in ON, sum their P&L under the managed exit. Result: gate strips 33 bear trades netting **+$917 IS** (13 wins +$2,759 / 20 losses -$1,841) = suppresses a NET-WINNER set. The managed chandelier+ITM exit lets the bear winners RUN and caps the losers, so trades the gate used to correctly kill (small OTM winners, big wide-stop losers) are now net-positive.

**Sign-UNstable** across IS sub-windows: helps W1 2025H1 (-$888 removed) but HURTS W2 2025H2 (+$937) and W3 2026Q1 (+$972) — the two largest recent windows. OP-22: fails G1(IS_delta -$676), G3(WF -5.73 sign-flip), G4(SW 2/4 hurt). Only G2(OOS +$775, n=5 thin) and G5(anchor, near-vacuous — engine takes ~0 trades on the J anchor dates) pass.

**Param diff to unblock:** `require_bearish_fill_bar` true→false in `automation/state/aggressive/params.json` (Bold). Safe unchanged.

**Confidence 6/10** — NOT a slam-dunk: OOS (n=5) still leans the gate's way and it's a look-ahead gate (live value already softer). But the IS removed-set inversion is a real mechanism-level "now blocks winners" signal.

**Methodology that worked (reuse for other block re-vals):** don't trust aggregate delta alone (cascade artifacts, L15) — compute the DIRECT removed-set net P&L by trade-identity diff (entry_time+side+strike), then check its sign-stability per sub-window. Tools: `backtest/tools/fill_bar_revalidate_current_engine.py` + `fill_bar_removed_trades_audit.py`. Anchor (OP-16) days 4/29–5/06 fall in the IS window, not OOS — check anchors in the IS run; engine barely trades the exact J dates so anchor is near-vacuous no-regression, not an endorsement.

Related: [[project_direction_block_inventory]] (most bull/direction blocks ratified on OLD engine = stale). Sibling re-vals (entry_bar_body_pct_min #13, midday_trendline_gate) found the SAME stale-bear-block-removes-winners pattern under managed exits.
