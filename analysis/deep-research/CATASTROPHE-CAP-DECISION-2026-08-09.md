# CATASTROPHE-CAP DECISION — 2026-08-09

**Verdict: the shipped −50% catastrophe cap is VALIDATED by forward fires. Zero of three alternative widths clears the pre-registered gates. The watch closes.**

Prereg: [`prereg-catastrophe-cap-decision-2026-08-09.json`](../recommendations/prereg-catastrophe-cap-decision-2026-08-09.json), frozen **before** the runner. Runner: [`catastrophe_cap_decision_2026_08_09.py`](../../backtest/tools/catastrophe_cap_decision_2026_08_09.py). Scorecard: [`catastrophe-cap-decision-2026-08-09.json`](../recommendations/catastrophe-cap-decision-2026-08-09.json).

## Why this ran tonight

The CATASTROPHE-CAP-WIDEN-WATCH accrual reached its **own** pre-registered bar during tonight's nightly: `n_fires=13 >= decision_n=10`, `ready_for_decision=true`. The 2026-07-23 shakeout study that opened the watch explicitly forbade deciding on its n=4 sample (*"Do NOT widen on n=4"*) and instructed exactly this study. The instrument asked for the decision; this is it.

## Result — 13 real catastrophe-cap fires, real OPRA

| arm | total $ | Δ vs control | beats control | G_AGGREGATE | G_MAJORITY | G_DROP_BEST | G_TAIL | worst fire |
|---|--:|--:|--:|:-:|:-:|:-:|:-:|--:|
| **CONTROL (−50%)** | **−3,056.00** | — | — | — | — | — | — | −664.00 |
| CAP_60 | −3,968.40 | −912.40 | 1/13 | ❌ | ❌ | ❌ | ❌ | −520.80 |
| CAP_70 | −3,236.50 | −180.50 | 2/13 | ❌ | ❌ | ❌ | ✅ | −520.80 |
| NO_CAP_HOLD_TO_EOD | −2,338.00 | **+718.00** | 4/13 | ✅ | ❌ | ❌ | ❌ | −708.00 |

**Survivors: none.**

## The one number that looked like a win, and why the prereg killed it

`NO_CAP_HOLD_TO_EOD` is **+$718 better in aggregate** — the headline the accrual had been flashing for a week. It fails anyway, on three independent pre-registered gates:

- **G_MAJORITY: 4 of 13.** Holding was better on fewer than a third of the fires. The aggregate is carried by a small number of large recoveries; the median fire was *worse* held.
- **G_DROP_BEST:** remove the single fire where holding gains most and the advantage does not survive.
- **G_TAIL:** worst single fire deepens from **−$664 to −$708**. Widening the last backstop necessarily deepens the tail, and the tail is the entire reason the backstop exists.

The majority gate was written into the prereg *specifically* to stop a couple of big recoveries from carrying a rare-tail decision, and it was written knowing the aggregate already favoured holding. It did its job.

## This contradicts the replay gradient — and the real fires win

Earlier the same evening, the 96-cell [entry × exit matrix](ENTRY-EXIT-MATRIX-2026-08-09.md) found the **opposite-signed** gradient: tightening worse (−25% ≈ $1/tr vs −50% ≈ $16/tr), widening to −60% mildly better (≈$20/tr), removing the cap better still (≈$40/tr).

Both are real measurements of **different questions**:

- The **matrix** prices the cap across replay trades where it is one of several exits competing to fire. Most of those trades never touch the cap at all, so the "cap width" column is largely measuring *other* exits' behaviour under a nominal setting.
- **This study** prices only the 13 events where the cap **actually fired** — a conditional-on-firing, rare-tail population, on real broker fills.

For the question *"should we loosen the live catastrophe cap?"* the conditional-on-firing population is the one that matters, and it says **no**. Recorded rather than adjudicated silently, per the prereg's own rule.

**Practical consequence:** the standing "kill the −50% cap" thread is **closed against loosening**. Tightening was already killed by the matrix. Both directions are now measured, and the shipped value survives both.

## What did NOT happen

Nothing was flipped. `params.json`, `aggressive/params.json`, `exit_manager.py` and every fleet arm's cap are untouched. n=13 is small for a tail statistic, and the prereg pre-committed that no arm ships from this study regardless of outcome.

## Watch status

`CATASTROPHE-CAP-WIDEN-WATCH` → **CLOSED, cap validated.** The accrual keeps running (it is free and rides the existing nightly), but it is no longer gating a pending decision. If a future width is proposed it needs a fresh pre-registration and must beat these four gates on a larger n.

## Reproduce

```bash
backtest/.venv/Scripts/python.exe backtest/tools/catastrophe_cap_decision_2026_08_09.py
```
