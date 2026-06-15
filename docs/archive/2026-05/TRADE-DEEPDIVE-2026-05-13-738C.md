# Trade Deep-Dive: 2026-05-13 738C × 15 — Engine's +$2,932 Banger

_Generated 2026-05-13T21:15 ET. J's request: "have we walked back through today and dialed in the trade we did good on to perfect it further?"_

## TL;DR (J's words)

> "The exit is perfect 13:55 red candle. That is flawless execution and watching the exit and letting the runner run. The entry is really good too — we bounced off that line at 11:30 and then entered after, chef's kiss."

**Engine did flawless ribbon-ride execution. The win pattern is locked in. The refinements needed are SIZING + STRIKE SELECTION for the $1K starting account.**

---

## Full timeline (UTC → ET, EDT = UTC -4)

| ET Time | Action | Price | Qty | Cumul P&L | Notes |
|---|---|---|---|---|---|
| 09:31 | Legacy SPY 200-share liquidation | $737.46 | 114 | — | Pre-existing assignment from 5/12 738C, queued from yesterday |
| 09:33 | Legacy SPY (rest) | $737.47 | 86 | — | Account flat in equity post-fill |
| 09:50 | **BUY 15× SPY 734P @ $0.75** | $0.75 | 15 | -$1,125 cost | Bear setup (after J's 09:30 short already played out) |
| 10:00 | SELL 15× 734P @ $0.54 (stop) | $0.54 | 15 | **-$315** | Late-entry into J's already-played dump; got stopped on the bounce |
| **11:38** | **🟢 BUY 15× SPY 738C @ $2.10** | $2.10 | 15 | -$3,150 cost | **THE WIN: BULLISH_RECLAIM_RIDE_THE_RIBBON** |
| 12:13 | SELL 7× 738C @ $2.80 (TP1) | $2.80 | 7 | **+$490** | TP1 fired at +33% premium (locks profit) |
| 15:45 | SELL 6× 738C @ $5.43 (auto-liquidate) | $5.43 | 6 | **+$1,998** | Alpaca's auto-liquidation rule for ITM 0DTE near expiry |
| 15:55 | SELL 2× 738C @ $4.32 (EOD safety) | $4.32 | 2 | **+$444** | Last 2 contracts, EOD safety net |

**738C net: $6,082 proceeds - $3,150 cost = +$2,932 (+93%)**
**Net engine day: -$315 (734P) + $2,932 (738C) = +$2,617**

---

## ✅ What WORKED — lock these in

### 1. Entry timing (J's "chef's kiss")

**11:30 bar = 738.10 reclaim on volume + ribbon BULL 49c spread + HTF BULL + VIX 18.04 falling + bull score 11/11.**

Engine waited for ALL of:
- Level reclaim on a 5m closed bar (not intraday touch)
- Volume confirmation (131% of 20-bar avg per the journal)
- Ribbon stack BULL with ≥30c spread (not chop)
- HTF 15m alignment BULL
- VIX direction = falling (calm tape, not panic-selling)
- Bull score 11/11 (max)

Entered at 11:38 ET = the NEXT bar after the reclaim (avoided the wick, took the confirmed close).

**Lesson:** the multi-condition gate filtering is RIGHT. v14 production heartbeat does this correctly. Don't loosen.

### 2. The ribbon ride (J's favorite)

After entry, ribbon expanded BULL 49c → 76c → 96c → 139c by the afternoon. Stack stayed BULL all session. SPY drove 738.10 → 743.79 (+$5.69 over 4 hours).

**Lesson:** when ribbon STAYS aligned + spread WIDENS, the runner pays. The engine correctly held 8 contracts past TP1 to capture this.

### 3. Exit cascade

| Exit | Time | Pct Premium | Why |
|---|---|---|---|
| TP1 | 12:13 | +33% | Lock half profit, leave runner |
| Auto-liquidate | 15:45 | +159% | Alpaca's protection vs ITM-0DTE expiry — caught near top |
| EOD safety | 15:55 | +106% | Last 2 contracts, mechanical |

Best exit was the AUTO-LIQUIDATE at $5.43 (caught near the day's high $743.79). The EOD net was lower because spot pulled back slightly into close.

**Lesson:** the auto-liquidate (Alpaca's automatic ITM-0DTE close) is FREE alpha. We should NOT try to outsmart it — it caught the local top better than any time-based exit would have.

---

## 🔧 What to REFINE — for the $1K starting account

### CRITICAL: Sizing is too rich for $1K account

**Today's actual sizing:** 15 contracts × $2.10 = **$3,150 cost**
**As % of $1K account:** **315%** — would be impossible (no margin available; would require $25K+ account).
**As % of $98K real account:** 3.2% — reasonable.

**The problem:** CLAUDE.md says "$1K starting" but actual paper account is $98K. Engine sized for $98K (qty=15 per v14's tier_3) which is correct for that balance. But J intends to TRADE AS IF $1K account (the growth ladder).

**Fix recommendation:**
- **For $1K-$2K account: qty=2-3 contracts max** (per CLAUDE.md sizing tier_1)
- **For $2K-$10K account: qty=5 base / 8 elite**
- **For $10K-$25K account: qty=10 base / 15 elite**
- **For $25K+: qty=10 base / 15 elite** (current tier_3, which engine used)

### CRITICAL: Strike selection too rich for $1K account

**Today's actual strike:** 738C with SPY at $739.10 = **ITM-1** (intrinsic $1.10 + extrinsic $1.00 = $2.10 premium).

**For $1K account, you'd want OTM strikes** (cheaper premium, higher % gains, smaller dollar loss if stopped):

| Strike | Distance from spot | Approx premium | 3-contract cost | % of $1K |
|---|---|---|---|---|
| 738 (ITM-1) | $1 ITM | $2.10 | $630 | 63% (TOO RICH) |
| 740 (ATM) | $1 OTM | ~$1.00 | $300 | 30% (acceptable) |
| 741 (OTM-2) | $2 OTM | ~$0.60 | $180 | 18% (lean) |
| 742 (OTM-3) | $3 OTM | ~$0.35 | $105 | 11% (very lean, J's style) |
| 743 (OTM-4) | $4 OTM | ~$0.20 | $60 | 6% (max-leverage) |

**J's actual 5/13 trade** was 736P × 5 @ $0.77 (4 strikes OTM from $738.46 entry spot) = $385 cost = 38% of $1K. Lean + high-payout.

**If engine had used J's pattern** (3 contracts × 740C @ $1.00 instead of 15× 738C @ $2.10):
- Cost: $300 vs $3,150 (10× cheaper)
- TP1 at +33% gain: $99 profit (vs $490)
- Final exit at +159% gain (auto-liquidate): $477 profit (vs $1,998)
- **Total ~$576 profit on $300 cost = +192%** (vs +93% on the actual trade)
- **Better dollar return per dollar risked.**

**Lesson:** for the $1K starting account, OTM strikes (3-5 dollars OTM) at qty=3 produce HIGHER % returns with LOWER dollar risk. The engine should bias OTM for tier_1 sizing.

### MEDIUM: The 09:50 bear entry was late

**734P entry at 09:50 ET = SPY $735.50 area.** J had already exited the move at 09:48 ET when SPY bounced off 736.

The engine entered AFTER the bottom was in. Got stopped 10 min later for -$315.

**Why this happened:** v14 heartbeat was BLOCKED by the 10:00 ET time gate until 10:00. The 734P entry at 09:50 was the WATCHER (no time gate) firing — but the watcher fired AFTER the cascade had completed.

**Fix recommendation:**
- Watchers should EITHER fire FAST (within first 1-3 bars when J's pattern develops) OR not fire at all
- The 09:50 entry was the WORST window: too late for the open-fade, too early for v14's main session
- PFF strategy (shipped today 12:02 ET) should catch this on tomorrow's open

---

## Recommended doctrine update for J's review

### New params.json sizing rules (proposed for J ratification)

```jsonc
{
  "qty_tiers": {
    "$1k_to_$2k":  { "base": 2, "elite": 3, "max_premium_pct_of_account": 0.40 },
    "$2k_to_$10k": { "base": 3, "elite": 5, "max_premium_pct_of_account": 0.30 },
    "$10k_to_$25k": { "base": 5, "elite": 8, "max_premium_pct_of_account": 0.25 },
    "$25k_plus":   { "base": 10, "elite": 15, "max_premium_pct_of_account": 0.20 }
  },
  "strike_offset_per_tier": {
    "$1k_to_$2k":  { "bear_otm": 4, "bull_otm": 4 },     // 4 strikes OTM (J's style — lean+leveraged)
    "$2k_to_$10k": { "bear_otm": 3, "bull_otm": 3 },     // 3 strikes OTM
    "$10k_to_$25k": { "bear_otm": 2, "bull_otm": 2 },    // ITM-2 (current v14)
    "$25k_plus":   { "bear_otm": 2, "bull_otm": 2 }      // ITM-2 (current v14)
  }
}
```

The `max_premium_pct_of_account` cap is a HARD GATE: if (qty × premium × 100) > (account_equity × max_premium_pct), engine reduces qty until it fits. Prevents 315%-leverage situations like today.

### New v14e knob: `prefer_otm_for_small_account`

If account < $10K → bias strike selection OTM by +1 to +3 strikes from current default. Captures J's lean-+-high-payout style.

---

## What to encode into the engine's doctrine permanently

1. ✅ **Multi-condition entry gates work.** Don't loosen.
2. ✅ **Ride the ribbon when stack stays aligned + spreads widen.** Hold runner past TP1.
3. ✅ **Trust Alpaca's auto-liquidate near 0DTE expiry.** Don't try to outsmart with time-based exits.
4. ⚠️ **Size to ACCOUNT ladder, not just current balance.** $1K starting = 2-3 contracts MAX, OTM strikes preferred.
5. ⚠️ **Watcher entries that fire too late (after the move) are worse than no entry.** Need timing-of-fire calibration.
6. ⚠️ **PFF strategy now LIVE for tomorrow's open** — captures J's open-fade window the engine missed.

---

## Action items for J's morning ratification

1. **Approve the sizing tier table above?** (Currently the engine has v13 tiers in `automation/state/params.json` — propose updating bear branch to v14_enhanced + adding the per-tier strike_offset rules.)
2. **Approve OTM bias for small accounts?** (Engine would pick 740C-742C instead of 738C on a $1K account.)
3. **Watch tomorrow's PFF + production v14** — if PFF catches your open-fade pattern AND v14 catches another bull-reclaim, that's 2 confirmation days.

---

## Files for J's review

- This doc: `docs/TRADE-DEEPDIVE-2026-05-13-738C.md`
- Full journal: `journal/2026-05-13.md`
- Morning brief: `docs/MORNING-BRIEF-2026-05-14.md`
- v14_enhanced ratification: `docs/MONDAY-READY-CHECKLIST-V14_ENHANCED-2026-05-13.md`
- Production sizing rules (current): `strategy/risk-rules.md`
- Account context: `CLAUDE.md` (search "Sizing tiers")

---

**Bottom line:** Engine's execution was 9/10 (entry pattern + ribbon ride + exit cascade all flawless). The 1-point demerit is sizing/strike selection for the intended $1K account ladder. Fix sizing rules + add OTM bias = **10/10 trade pattern locked in for the engine going forward.**
