# 🕰️ Shadow & Prereg Board

> Auto-generated `2026-08-11 18:55:07 Tuesday EDT` by obsidian_vault_sync.py. Shadow tallies update nightly; a missing tally means that instrument has not fired yet.

## Live shadow instruments

- **Score ladder** (`Gamma_LadderRungShadow`, 16:40 ET) — 4 session rows; latest: `{"date": "2026-08-11", "arm_id": "risky-1", "rung": 8, "tallied_at": "2026-08-11T14:40:04.672657", "est": false, "n_added": 13, "added_pnl": -105.0, "binary_day_pnl": 63.5, "ladder`
- **V-d1 / V-e3 entry shadow** (16:25 fold) — artifact: `analysis\entry-quality\shadow-tally.jsonl`
- **Chop exposure meter** (`Gamma_ChopMeter`, 16:08 ET) — artifact appears after the next close.

- **stop_mode premium-vs-structure** (16:25 fold) — ⚠️ **INPUT STALE** — the ledger stopped feeding it; counts are frozen.
- **Direction symmetry** (16:25 fold) — **RED**: 4 asymmetric knobs, 4 gates on stale evidence, 26 phantom documented knobs → [[analysis/deep-research/DIRECTION-SYMMETRY-AUDIT-2026-08-09]]

## Frozen preregs — auto-discovered

- `STRUCTURE-STOP-ZONE-2026-08-11` — [[analysis/recommendations/prereg-structure-stop-zone-2026-08-11]]
- `TIGHT-STOP-VWAP-2026-08-11` — [[analysis/recommendations/prereg-tight-stop-vwap-2026-08-11]]
- `REGIME-CONDITIONAL-EXIT-2026-08-11` — [[analysis/recommendations/prereg-regime-conditional-exit-2026-08-11]]
- `GIVEBACK-RATCHET-2026-08-10` — [[analysis/recommendations/prereg-giveback-ratchet-2026-08-10]] · does **not** ship on its own evidence
- `TRIGGER-PARITY-BULL-2026-08-09` — [[analysis/recommendations/prereg-trigger-parity-2026-08-09]] · does **not** ship on its own evidence
- `LADDER-X-PREMIUM-2026-08-09` — [[analysis/recommendations/prereg-ladder-x-premium-2026-08-09]] · **blocked**, deliberately unrun
- `CATASTROPHE-CAP-DECISION-2026-08-09` — [[analysis/recommendations/prereg-catastrophe-cap-decision-2026-08-09]] · does **not** ship on its own evidence
- `STOP-MODE-LIVE-ARM-RISKY3-2026-08-09` — [[analysis/recommendations/prereg-stop-mode-live-arm-risky3-2026-08-09]]
- `STOP-MODE-STRUCTURE-VS-PREMIUM-2026-08-09` — [[analysis/recommendations/prereg-stop-mode-structure-vs-premium-2026-08-09]]
- `TRENDLINE-ENGINE-VALIDATION-2026-08-09` — [[analysis/recommendations/prereg-trendline-engine-validation-2026-08-09]]
- `prereg-entry-exit-matrix-2026-08-09` — [[analysis/recommendations/prereg-entry-exit-matrix-2026-08-09]]
- `prereg-profitability-2026-08-08` — [[analysis/recommendations/prereg-profitability-2026-08-08]]
- `GATE-REVALIDATION-2026-08-08` — [[analysis/recommendations/prereg-gate-revalidation-2026-08-08]]
- `prereg-ribbon-flipback-buffer-v2-2026-08-08` — [[analysis/recommendations/prereg-ribbon-flipback-buffer-v2-2026-08-08]]
- `prereg-ribbon-flipback-buffer-2026-08-08` — [[analysis/recommendations/prereg-ribbon-flipback-buffer-2026-08-08]]
- `SCORE-LADDER-V2-DEMERIT-2026-08-07` — [[analysis/recommendations/prereg-score-ladder-v2-2026-08-07]]
- `prereg-runner-finite-tgt-candidate-2026-08-06` — [[analysis/recommendations/prereg-runner-finite-tgt-candidate-2026-08-06]]
- `prereg-runner-be-floor-2026-08-06` — [[analysis/recommendations/prereg-runner-be-floor-2026-08-06]]
- `TP1-REACHABILITY-2026-08-06` — [[analysis/recommendations/prereg-tp1-reachability-2026-08-06]]
- `LEVER-CATCAP-2026-08-06` — [[analysis/recommendations/prereg-lever-catcap-2026-08-06]]
- `BULL-VIX-SOFT-MODE-SOLE-BLOCKER-2026-08-03` — [[analysis/recommendations/prereg-bull-vix-soft-mode-2026-08-03]]
- `PRETP1-BE-FLOOR-ISOLATED (iteration 4 of the exit-leak arm axis)` — [[analysis/recommendations/prereg-pretp1-be-floor-isolated-2026-08-02]]
- `prereg-bold-selective-fallback-2026-08-02` — [[analysis/recommendations/prereg-bold-selective-fallback-2026-08-02]]
- `prereg-bold-adaptive-sizing-2026-08-02` — [[analysis/recommendations/prereg-bold-adaptive-sizing-2026-08-02]]
- `REGIME-STANDDOWN-EARLY-CLASSIFIER-2026-08-02` — [[analysis/recommendations/prereg-regime-standdown-2026-08-02]]
- _+29 older preregs on disk (see `analysis/recommendations/prereg-*.json`)_

## Frozen preregs — curated (richer write-ups)

- **TP1 sell-half at +100% (R_tp100_f50)** → [[analysis/deep-research/TP1-REACHABILITY-2026-08-06]]
- **Runner finite 2.5x target** → [[analysis/deep-research/HOLD-WINNERS-2026-08-06]]
- **B-RR-070 range compression** → [[analysis/deep-research/CHOP-DEFENSE-2026-08-06]]
- **BRK600 / CAP-3 / CONSEC4 loss guards** → [[analysis/deep-research/KEEP-LOSSES-SMALL-2026-08-06]]
- **F10 recalibration on live feed** → [[analysis/deep-research/FRIDAY-2026-08-07-FULL]]
- **Score ladder (held at gate)** → [[analysis/deep-research/CLOSE-EXECUTION-2026-08-07]]

## Doctrine anchors

- [[analysis/deep-research/WEEK-ORDER-2026-08-10|THE WEEK ORDER]] · [[automation/overnight/STATUS|STATUS]] · [[markdown/doctrine/LESSONS-LEARNED|Lessons]]
