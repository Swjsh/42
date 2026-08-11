# A harness "calibrated to near-zero bias" can be two large errors cancelling — the anchor must decompose, not just total

**Date:** 2026-08-11 night
**Where:** `backtest/tools/harness_fidelity_anchor.py` / `multileg_exit_walk.py` calibration
**Class:** C7 sibling (a passing total masking two failing parts) + L294 (sibling copies break identically)

## Symptom

The exit-replay harness anchored at **+$384 total bias over 182 real positions** — celebrated
as near-perfect calibration — while carrying TWO large opposing defects:
- its SPY feed silently ended 2026-07-22 (pick-biggest-file cache selection), so structure
  stops could not fire on any later date → strongly OPTIMISTIC on recent positions;
- a 2¢/contract slippage assumption → broadly PESSIMISTIC everywhere.

The totals cancelled. Fixing only the feed exposed the truth: the "calibrated" harness was
−$4,166 at the old slippage. True calibration (v5): `extreme` fills + 1¢ slippage + full
SPY union feed → −$7.4/pos, 95% sign agreement.

## Root causes (two, both one sentence)

1. The anchor scored calibration on the **aggregate total**, which can be zero while its
   components are large and opposite — it must also gate on **directional balance** and on
   **error decomposition by cohort** (hold-longer vs matched vs sooner; by stop_mode).
2. The SPY-cache coverage bug had already been found and fixed in `regime_shadow_counter.py`
   the same evening, but the **sibling copy** in the anchor was not swept (L294: copy-pasted
   loaders break identically across every sibling on the same trigger).

## The rule going forward

- A fidelity anchor PASSES only if: |total bias| small AND optimistic/pessimistic counts
  roughly balanced AND no single cohort (by stage, stop_mode, or hold-delta bucket) carries
  a large signed error. Total-only calibration is inadmissible.
- Any bug found in a data loader triggers an immediate grep for sibling loaders of the same
  source before the fix is declared done.

## Cross-refs
- `analysis/deep-research/2026-08-11-audit/HARNESS-CALIBRATION.md` (v1→v5 table)
- Prior sibling lesson: 2026-08-10 population-ab-control-cannot-express-live-baseline
