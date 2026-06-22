# J-PARAM-TWEAKS — the "just tweak certain parameters" mandate, done rigorously

> J (2026-06-20): *"there has to be something profitable if we just tweak certain parameters."*
>
> Angles B1 (strike), B2 (hold-time/time-stop), B3 (TP target) from
> [markdown/research/J-DATA-RESEARCH-MASTER-PLAN.md](J-DATA-RESEARCH-MASTER-PLAN.md). These are the
> literal parameter tweaks. This doc reports his optimal value for each AND whether it
> validates forward on OUR data.

## Method (the anti-overfit guard)

| Step | Source | Role |
|---|---|---|
| **Part A** | His Webull winners (`analysis/webull-j-trades/`) | **DEFINES** the candidate value |
| **Part B** | OUR 2025-26 SPY **real OPRA fills** | **VALIDATES** it forward (OOS / WF / all-cuts / DSR / drop-top5 / both-dirs) |

A value "optimal on his data" with **no OUR-data OOS lift = DEAD (overfit)**, not a win.

- Part A: `backtest/autoresearch/j_param_tweaks_partA.py` → `analysis/recommendations/_j_param_partA.json`
- Part B: `backtest/autoresearch/j_param_tweaks_partB.py` → `analysis/recommendations/_j_param_partB.json`
- Scorecard: `analysis/recommendations/j-param-tweaks.json`
- Fills: `lib.simulator_real.simulate_trade_real` (causal next-bar-open, v15 exit stack, chart-stop-only). **Not rebuilt.**
- Detectors validated: **gap_and_go** (LIVE bear edge) and **j_vwap_continuation** (flip-ready edge).
- Scale verified: his bar cache + `entry_close` are SPY-scale; SPX strikes ÷10 (median ratio 10.03), SPY ×1. Moneyness on the common SPY scale.

---

## Verdicts at a glance

| Param | His-data optimal | Forward on OUR data | Tag |
|---|---|---|---|
| **B1 strike** | OTM-1/OTM-2 (sharpest multiple) | **ITM-1 on gap-and-go: +$35/trade (+42%) OOS, all gates pass.** His OTM preference does NOT transfer. | **SHIP** |
| **B2 hold** | peak ~30 min; he exits ~14 min | No early time-stop robustly beats live 15:40. | **DEAD** |
| **B3 TP** | low (~15% median peak gain) | His low-TP is INVERTED forward; live tp1=0.50 re-confirmed optimal (no change). | **WATCH** (confirms current) |

**One ship-grade tweak: gap-and-go strike ATM → ITM-1.** The other two of his preferences are overfit to his SPX-winner distribution and die forward — which is exactly what the method exists to catch.

---

## B1 — STRIKE  →  **SHIP** (gap-and-go ATM → ITM-1)

**His data (SPX 0DTE winners, by moneyness-at-entry):**

| bucket | n | mean multiple (exit/entry) | $/contract | WR |
|---|---|---|---|---|
| OTM-1 | 60 | **1.19** | +38.7 | 75% |
| OTM-2 | 73 | 1.19 | **+43.5** | 60% |
| OTM-3+ | 323 | 1.14 | +26.3 | 57% |
| ATM | 6 | 0.90 | +4 | — (tiny n) |
| ITM-1 | 2 | 0.80 | −30 | — (tiny n) |

→ His sharpest risk/reward was **modest-OTM (OTM-1/OTM-2)**, not ATM/ITM, not deep-OTM lottery tickets.

**OUR data (forward validation — his OTM preference does NOT transfer):**

Gap-and-go at the **true live settings** (tp1=0.50, tp1_qty=0.667, time_stop=15:40, chart-stop-only):

| strike | n | exp $/trade | **OOS exp $/trade** | total $ | WR | all-cuts-OOS+ | both-dirs+ | DSR | drop-top5 |
|---|---|---|---|---|---|---|---|---|---|
| ATM (current) | 84 | +63.0 | +83.8 | +5,292 | 66.7% | ✅ | ✅ | PASS | +33.4 |
| **ITM-1 (new)** | 85 | +81.7 | **+119.1** | **+6,947** | 64.7% | ✅ | ✅ | PASS | +49.9 |

**+$35.3/trade (+42%) OOS, +$1,655 total. Every structural gate passes.** WR dips 2pp — the deeper-delta tradeoff (ITM-1 has higher delta / less theta, so it captures more of the gap-continuation $-move). The strike×TP grid confirms ITM-1 dominates ATM/OTM-1 at **every** TP level (not an artifact):

| | tp0.15 | tp0.30 | tp0.50 |
|---|---|---|---|
| **ITM-1** | 63 | 74 | **110** |
| ATM | 56 | 54 | 79 |
| OTM-1 | 53 | 55 | 76 |

`j_vwap_continuation`: ITM-1 is its best strike too (**WATCH**, +$11 OOS) but its baseline fails strict all-cuts-OOS+, so no knob can reach SHIP there.

### Exact param change (B1)

```
File: backtest/lib/watchers/gap_and_go_watcher.py
  DEFAULT_STRIKE_OFFSET: int = 0   ->   -1     # ATM -> ITM-1  (line ~76)
  (and the "strike_offset" entry in the go-live params dict, ~line 261)
```

- **Effect:** gap-and-go enters ITM-1 (strike $1 ITM) instead of ATM.
- **Guard:** ships under OP-22 (ship-validated-wins) — OOS+, WF≥0.70, all-cuts-OOS+, DSR-PASS, both-dirs+, drop-top5-robust all PASS.
- **Scope:** this is a **per-setup override for gap-and-go** (like its per-setup chart-stop-only override), not the account-tier strikes (Safe OTM-2 / Bold ITM-2) that govern the general book. Bold's ITM-2 tier is already deeper than ITM-1 — consistent with the finding's direction.
- `gap_and_go_enabled` is still `false` in `params.json` (detector inert until J flips live); this tunes the strike the detector **will** use. OP-21 live-gate (3 live J confirmations) still stands. **J holds REVOKE.**

---

## B2 — HOLD / TIME-STOP  →  **DEAD**

**His data:** median **minutes-to-peak = 29 min** (50.8% peak by 30 min, 70% by 60 min, 84% by 120 min). He typically *exited even earlier* (actual hold median **14 min**). Reads as "cut the long tail."

**OUR data:** no early hard time-stop produced a robust OOS lift over the live **15:40**:

| gap-and-go time-stop | 11:00 | 11:30 | 12:00 | 13:00 | 15:50 |
|---|---|---|---|---|---|
| OOS lift vs 15:40 | +$3.9 | −$6.0 | −$13.8 | +$0.4 | +$7.2 |

The only positive cells (11:00, 13:00) have negligible lift and no monotone structure; **mid-day stops (11:30/12:00) clipped winners** (DEAD). On `j_vwap_continuation` early stops were WATCH-only.

**Why his-data optimum dies forward:** "peak ~30 min" is a **winner-only** statistic. On OUR full tape (winners + losers) an early hard clock clips the runners that pay for losers. The **v15 chandelier trailing-stop already captures "lock in before the fade" dynamically** — better than a static clock (C28: exit tuning has diminishing returns once the dynamic trail is in place).

### Exact param change (B2)
**NONE** — keep `time_stop_et = 15:40`. Early time-stop is overfit to his winner-peak distribution.

---

## B3 — TP TARGET  →  **WATCH** (re-confirms current 0.50; his low-TP rejected)

**His data:** median peak gain only **~14.6%** (44% reach +20%, 29% reach +30%, 18% reach +50%). Reads as "use a low TP1 (~15%) to bank winners before the fade."

**OUR data — his low-TP is INVERTED forward.** Among {0.10, 0.15, 0.20, 0.30, 0.50} the OOS-optimal TP1 is **0.50**, and a LOW TP1 hurt:

| gap-and-go tp1_pct | 0.10 | 0.15 | 0.20 | 0.50 |
|---|---|---|---|---|
| OOS lift vs 0.30 | −$20.6 | +$1.9 | −$25.4 | +$24.7 |

**Critical correction (L110-class):** the sweep baseline used `tp1_pct=0.30` (the *simulator default*), but the **live value is already 0.50** (Safe `params.json`) / 0.75 (Bold). So the "+$24.7 lift" is vs a non-live default — against reality **there is no change to ship**; the sweep independently **re-confirms the current 0.50 is optimal**.

**Reconciliation:** his ~15% is where *his winners peaked* (winner-only). On OUR tape, banking half at +15% caps the winners that must offset the losers → a higher TP1 wins forward. Different questions, not a contradiction. His-data-derived value (low TP) = **DEAD**; the live high TP **stands**.

### Exact param change (B3)
**NONE** — keep `tp1_premium_pct = 0.50` (Safe, already live & re-validated) / `0.75` (Bold, above grid, not contradicted). His low-TP candidate rejected as overfit.

---

## Caveats

- **Proxy strikes (L58):** nearest-cached real-OPRA strike used; ITM-1 n=85 vs ATM n=84 (one extra cache hit) — immaterial.
- **B2/B3 peak path:** IV inverted from his own entry fill (no 2021-23 VIX) — self-calibrating per trade, more honest than a flat VIX proxy, but holds IV constant intrabar.
- **j_vwap_continuation** baseline fails strict all-cuts-OOS+ (most-recent OOS window, partial OPRA coverage) — WATCH_ONLY class like the shipped H4; no knob there can SHIP.
- **Propose-only (Rule 9).** The ITM-1 change tunes the dormant gap-and-go detector; flip `enabled` + 3 live J confirmations (OP-21) before any live order path. J holds REVOKE.
