# G2 trendline-bypass — RE-RUN VERDICT (2026-08-20)

> **Question asked:** "why did we only trade the last 2 hours, and how could we have made more money today?"
>
> **Answer: the obvious lever is dead. It has now been measured twice, and the fresher data killed it harder.**

---

## Why this was re-run at all

The 2026-08-01 study returned NEITHER_SHIPS, but the *reason* mattered:

| arm | full Δ | recent Δ | G1 (primary) | verdict |
|---|--:|--:|---|---|
| ARM_EXTEND | −$2,061.65 | **+$1,616.15** | **UNDETERMINED** | NULL |
| ARM_REMOVE | +$2,693.55 | +$279.60 | UNDETERMINED | NULL |

G1 is the **primary** gate (J's recency-over-aggregate directive). For ARM_EXTEND it did not *fail* — it was **unmeasurable**, because 3 of the 25 recent days (2026-07-24, 07-27, 07-30) had **zero cached OPRA contracts**. An unmeasurable gate on a **+$1,616 recent window** is an open question, not a closed one.

Since then: OPRA partially backfilled, and **20 new trading days** rolled the recent-25 window forward to **2026-07-17 → 2026-08-20**, leaving only one zero-coverage day (today, whose contracts aren't cached yet).

**Re-run harness discipline:** `g2_trendline_bypass_ab_2026_08_20.py` overrides **only** the data window and the output paths. It asserts at startup that the five gates, both arms, and both scope values are unmutated, and it imports the 2026-08-01 measurement code byte-identical. If an arm looked good here, it had to be because the *data* changed.

---

## The result

| arm | scope | full Δ | recent Δ | G1 | G2 | G3 | G4 | G5 | verdict |
|---|---|--:|--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **ARM_EXTEND** | all_level_tied | +$78.15 | **−$561.55** | UNDET | **FAIL** | **FAIL** | PASS | PASS | **NULL** |
| **ARM_REMOVE** | none | −$984.70 | −$1,498.10 | **FAIL** | FAIL | FAIL | FAIL | PASS | **NULL** |

**FINAL: NEITHER_SHIPS_STAYS_TRENDLINE_ONLY.**

### ARM_EXTEND got *worse*, not better

| | 2026-08-01 | 2026-08-20 |
|---|---|---|
| Recent-window Δ | **+$1,616.15** | **−$561.55** |
| Trades added | 343 @ **−$10.42**/trade, WR 29.2% | 369 @ **+$3.36**/trade, WR 36.9% |
| G2 day-majority | PASS | **FAIL** (8 improved / 10 worsened) |
| G3 survives-drop-best | PASS | **FAIL** |

The per-trade economics of the added cohort *improved* (−$10.42 → +$3.36) — and the arm still got **further from shipping**, because the recent window flipped sign and two secondary gates fell. G3 failing means the recent delta was carried by a single trade; strip it and the rest is negative.

**A +$1,616 recent window that becomes −$562 on a rolled-forward window was never a signal.** It was noise that happened to be unmeasurable at the time.

---

## What this actually answers

Today, the raw detectors fired **`level_rejection` 108 times** and **`confluence` 67 times**, and **none converted** — they carry the full filter set including a VIX gate (`>17.30 AND rising`) that was unpassable at 15.49–16.13. It is natural to read those 175 detections as missed money.

**They are not.** ARM_EXTEND is precisely the experiment of letting them through, and across **232 trading days** it adds 369 trades worth **+$3.36 each** — statistically indistinguishable from zero before fees — while **losing $562 over the most recent 25 sessions** and worsening more days than it improves.

**The engine's behaviour today was correct.** It did not leave money on the table by holding until 12:56; it declined a cohort that does not pay.

---

## What is NOT closed by this

1. **The structural dependence is real and unresolved.** `filters.py` records that ~89% of bear ENTERs over 33 sessions come through the trendline-only bypass. Today it was 100%. That is a single-detector dependency, and this study says only that *the two obvious alternatives are worse* — not that the dependency is healthy.
2. **G1 is still UNDETERMINED for ARM_EXTEND** (today's OPRA isn't cached). It no longer matters — G2 and G3 both FAIL outright, so the arm cannot ship regardless — but the measurement gap itself persists and will recur.
3. **The genuine error today was trade 1**, not the gate: a long into BEAR ribbon + BEAR 15m + a BEARISH pre-registered bias, held 59 seconds for −$54. That is a real defect and it is *not* what this study examined.

---

## Ship decision

**Nothing ships. `trendline_bypass_scope` stays `'trendline_only'`.**

Two independent runs, overlapping-but-different windows, same conclusion — and the second one is stronger because it has fewer unmeasurable days and more evidence. The G2 asymmetry is **CONFIRMED as real** and **CONFIRMED as not worth acting on**.

_Source: `backtest/tools/g2_trendline_bypass_ab_2026_08_20.py` · pre-reg `prereg-g2-trendline-bypass-2026-08-01.json` (frozen 2026-08-01, unmodified) · full per-trade detail in `g2-trendline-bypass-2026-08-20.json`._
