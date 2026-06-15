---
name: project_v14e_structural_split
description: v14_enhanced_watcher score/direction structural split — score=11 is ALL bull/long (-$3,642), scores 6-10 are all bear/short (+$1,492). Bear-only gate is the proposed fix.
metadata:
  type: project
---

The v14_enhanced_watcher's aggregate -$2,150 over 502 observations is explained by a structural split:

- **score=11 → direction=long (BULL_RECLAIM_v14e):** N=242, WR=46.3%, total=-$3,940
- **score≤10 → direction=short (BEAR_REJECTION_v14e):** N=241, WR=58.5%, total=+$1,492

**Why:** In `evaluate_bearish_setup`, max bear score is 10/10. In `evaluate_bullish_setup`, max bull score is 11/11. So ALL score=11 observations in the v14e watcher are structurally long. The filter architecture, not data selection, determines this split.

**Best sub-tier:** Short + confidence=high (n_triggers≥3 + confluence): N=33, WR=84.8%, +$1,173.

**n_triggers=2 is the worst group:** -$3,924. Driven by [level_reclaim, confluence] bull 2-trigger pattern.

**Confluence=True is net-negative** (-$3,222) — driven by score=11 bull entries dominating the confluence bucket (150/214 confluence=True are score=11 bull).

**Proposed gate:** Remove BULLISH_RECLAIM_v14e branch from `v14_enhanced_watcher.py` detect function (lines 169-212). Watcher-only change — does NOT affect production heartbeat or params.json.

**Why:** The bull v14e engine fires at full score (11/11) before ribbon confirmation — `ribbon_flipped` is always False. The bearish engine requires score 6-10 with observable quality gradient.

**Filed:** `strategy/candidates/2026-05-21-v14e-quality-filter.md` (DRAFT)
