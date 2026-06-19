# backtest/autoresearch/_archive/sniper

The dead SNIPER autoresearch cluster, archived 2026-06-18 (de-sprawl Phase 3).
Git history is the canonical record.

24 standalone research scripts: SNIPER evaluators, real-fills/walk-forward
grinders, VIX-regime/VIX-trend filter experiments, the stage2/cs sweeps, plus
`t48_sniper_513_diag.py` and `t48_sniper_watcher_test.py`. The SNIPER strategy
never promoted (0 `_LEADERBOARD` citations, real-fills validation never landed),
and its scheduled task `Gamma_SniperShadowEOD` was retired the same day.

`t48_sniper_watcher_test.py` was **already broken** before archival — it imports
`lib.watchers.sniper_watcher` (`detect_sniper_setup`), a module that was deleted
in the 2026-06-18 watcher-engine overhaul, so it raised ImportError. Archived
as-is rather than fixed (the whole cluster is dead).

## KEPT (NOT archived) — still live
- `backtest/lib/sniper_detector.py` — consumed by `autoresearch/watcher_live.py`
  and `lib/{premarket_fail_fade,vwap_rejection,opening_drive_fade}_detector.py`
  and `lib/watchers/level_source.py`. **Do not archive.**
- Verified before archival: no live-path module imports any script in this folder.
