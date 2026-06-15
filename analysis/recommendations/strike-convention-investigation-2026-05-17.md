# Strike Convention Investigation — 2026-05-17

> Chef investigation. READ-ONLY. No code modified.

## 1. One-sentence verdict

**heartbeat.md is canonical and correct.** simulator_real.py uses an internally consistent but sign-inverted convention that the orchestrator bridges correctly for ITM-2 — but the orchestrator has no per-tier equity lookup, so all backtests run with ITM-2 regardless of account tier (a separate, more impactful bug).

---

## 2. ATM on 4/29 and J's actual strike

- J entry: 10:25:51 EDT, SPY 710P.
- 10:25 bar from `backtest/data/spy_5m_2025-01-01_2026-05-15.csv`: open=711.37, close=711.48.
- ATM = round(711.48) = **711**.
- J's 710P = strike 711 - 1 = **OTM-1** (put below spot = out-of-the-money, correct — J's account was ~$2K).
- Note: J traded pre-rules, before tier table existed. At $2K, current params would assign OTM-3 (strike 708), not OTM-1. J chose his strike manually; 710 was the nearest round level to the 711.4 resistance.

---

## 3. The conflicting code lines side by side

**heartbeat.md, line 254 (canonical):**
```
strike = round(spot) + strike_offset   # for BEAR puts
strike = round(spot) - strike_offset   # for BULL calls (mirror)
# Convention: positive offset = ITM, negative = OTM
# Example: offset=+2 -> put 2 above spot = ITM-2 (strike 713 with ATM=711)
# Example: offset=-3 -> put 3 below spot = OTM-3 (strike 708 with ATM=711)
```

**simulator_real.py, lines 280-283:**
```python
if side == "P":
    strike = atm - strike_offset    # offset -1 -> strike+1 (ITM-1 for puts)
else:
    strike = atm + strike_offset
# Convention: NEGATIVE offset = ITM, positive = OTM (sign-inverted vs heartbeat)
# Example: offset=-2 -> atm - (-2) = atm+2 = ITM-2 (strike 713) -- SAME RESULT
# Example: offset=+3 -> atm - 3 = atm-3 = OTM-3 (strike 708) -- SAME RESULT
```

**The formulas produce identical strikes IF the caller passes the sign-inverted value.**

**orchestrator.py, lines 262-265 (the bridge):**
```python
if "strike_offset_itm" in overrides:
    # params.json uses positive offset for ITM (2 = $2 in-the-money);
    # orchestrator uses negative for puts (strike_offset=-2 means $2 above spot for puts)
    kwargs["strike_offset"] = -abs(overrides["strike_offset_itm"])
```

The orchestrator reads `params.json: strike_offset_itm = 2` (positive, heartbeat convention) and converts to `-2` before passing to simulator_real. For ITM-2: `711 - (-2) = 713`. Correct.

---

## 4. Fix recommendation

### Which file is "wrong"

Neither file has a sign-convention bug in isolation — they are internally consistent, and the orchestrator bridge is correct for the ITM-2 case. **However:**

**The real bug is in the orchestrator's per-tier blindness.** `orchestrator.py` line 265 always passes `-abs(strike_offset_itm)` — a hardcoded ITM lookup. It has no code path for OTM tiers. For the new $1K paper accounts (OTM-3 tier in heartbeat), all backtests silently use ITM-2 (offset=-2) instead of OTM-3 (offset=+3 in simulator_real convention).

**Proposed 1-line orchestrator fix (DO NOT EXECUTE — propose only):**

Replace line 265:
```python
kwargs["strike_offset"] = -abs(overrides["strike_offset_itm"])
```

With a per-tier equity lookup (requires equity as a parameter to the overrides mapper — this is a multi-line change, not a 1-liner). The proper fix is to add `account_equity` to the overrides schema and replicate the tier table from heartbeat.md in a shared utility, then call `pick_strike_offset(equity, side)` at backtest entry. See `crypto/lib/strike_selection.py` which already has this logic.

**Minimal band-aid (1-line, but loses per-tier accuracy):**

If the intent is to test the $1K paper accounts (OTM-3), add a `strike_offset_otm` param to params.json and pass it through:
```python
# In orchestrator.py overrides mapper:
if "strike_offset_otm" in overrides:
    kwargs["strike_offset"] = abs(overrides["strike_offset_otm"])  # positive for simulator_real OTM
```

---

## 5. Side effects: are prior scorecards invalidated?

**Partial invalidation — depends on which account tier the backtest was run for:**

- All scorecards run with `params.json: strike_offset_itm = 2` (or any backtest that didn't override the tier): **correctly simulated ITM-2**. These are valid for the $25K+ equity tier.
- `v15.json`, `v15-final.json`, `v15.3.json`, and all weekend-research grinder outputs: were run via the orchestrator with `strike_offset_itm=2` → simulator_real offset=-2 → ITM-2. **These are correct for the $25K tier but wrong for the new $1K paper accounts.**
- The $1K paper accounts (Gamma-Safe-1 at $1K, Gamma-Bold-1 at $1K) are OTM-3 per heartbeat.md. The backtest engine was simulating ITM-2 for them. Strike 713 vs strike 708 on a $1K account with ATM=711 is a **5-strike gap** — premium at 713 would be ~2-3x higher than at 708. This inflates backtest dollar P&L relative to what the real $1K accounts will actually produce.
- **Quantitative impact rough estimate:** ITM-2 puts (delta ~0.55-0.65) vs OTM-3 puts (delta ~0.25-0.35). Entry premium ~$2-3 vs ~$0.30-0.50. The backtest P&L figures for "qty=3, $1K account" in recent scorecards overstate premium income by roughly 5-8x on the entry side. The percentage returns may be roughly consistent, but the dollar P&L is not representative.
- **The J anchor trades (4/29, 5/01, 5/04) were run with ITM-2 in backtest but J actually placed near-ATM or OTM-1 strikes manually.** These scorecards are partially misrepresentative of the live experience.

**Bottom line on scorecard validity:**
- Scorecards intended to model $25K+ equity with ITM-2: **VALID**.
- Scorecards intended to model the new $1K paper accounts: **INVALIDATED for dollar P&L** (percentage Sharpe may still be directionally informative).

---

## 6. Summary table

| File | Formula (puts) | Convention | Status |
|---|---|---|---|
| `heartbeat.md` L254 | `atm + offset` | positive=ITM, negative=OTM | CANONICAL (correct) |
| `simulator_real.py` L281 | `atm - offset` | negative=ITM, positive=OTM | Sign-inverted but internally consistent |
| `orchestrator.py` L265 | `-abs(params.strike_offset_itm)` | Bridges correctly for ITM tiers only | **BUG: no OTM tier lookup** |
| `crypto/lib/strike_selection.py` | `pick_strike(spot, equity, side, tiers)` | Same as heartbeat (positive=ITM) | Correct, full per-tier support |

---

CANONICAL CONVENTION = `atm + offset` (positive=ITM, negative=OTM). heartbeat.md is correct. simulator_real.py is internally consistent but sign-inverted. The real bug is orchestrator.py has no per-tier equity lookup — all backtests run as ITM-2 regardless of account size, invalidating dollar P&L figures for the $1K paper accounts.
