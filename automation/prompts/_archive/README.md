# _archive — retired prompt forks

Stale draft forks of production prompts, archived 2026-06-18 (de-sprawl Phase 3).
Git history is the canonical record of how these evolved.

| File | What it was |
|---|---|
| `heartbeat-v15-draft.md` | Pre-activation v15 heartbeat draft. v15 went LIVE 2026-05-13; production lives in `../heartbeat.md`. |
| `heartbeat-v15.2-draft.md` | Abandoned v15.2 sweep-blocker draft fork. |
| `heartbeat-v15.3-draft.md` | v15.3 live-price-trigger draft. Concluded additive-but-deferred (see `automation/overnight/queue.md` T-2026-05-17-04). |
| `premarket-v15-draft.md` | Pre-activation v15 premarket draft. Production lives in `../premarket.md`. |

NOTE: the live `heartbeat-v14-prod-backup.md` is **NOT** here — it is the documented
v15→v14 revert path and stays in `../` (referenced by `heartbeat.md`, `pin_chain_verify.py`,
`docs/V15-ACTIVATION-2026-05-13.md`).

`backtest/autoresearch/pin_chain_verify.py` was updated to read the two v15 drafts from
this archive path so it still reports their versions for situational awareness.
