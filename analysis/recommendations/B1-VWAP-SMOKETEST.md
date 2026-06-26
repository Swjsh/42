# B1 — VWAP_CONTINUATION LIVE-FIRE SMOKE TEST

**Verdict: `LIVE_EDGE_FIRES_OK`**  (run 2026-06-21T05:33:38)

Proves whether the one LIVE edge (`j_vwap_cont_enabled=true`) fires watcher -> heartbeat -> would-be-order end-to-end, or is silently broken. REPLAY/TRACE only — NO orders placed.

## Wiring facts
- `j_vwap_cont_enabled` **Safe-2** = `True` (LIVE), **Bold** = `False` (absent key -> inert on Bold)
- `j_vwap_cont_side` (Safe) = `both`; `j_vwap_cont_put_vix_gate` (Safe) = `True`
- watcher registered in live fleet (`runner.WATCHERS`): **True**
- Safe-2 ($2K) heartbeat strike tier: **OTM-2 (offset -2)** (heartbeat sign convention: NEGATIVE=OTM)

## Coverage (hard-windowed to OPRA cache)
- OPRA cache last day: `2026-05-29`; last real fill in this run: `2026-05-29`
- research signals total (2025-01..2026-05-29): 166; distinct signal dates in cache: 162
- smoke dates (most-recent in-cache): 2026-05-22, 2026-05-28, 2026-05-29

## Per-date end-to-end trace

| date | research side@time | live watcher | parity (side/time) | would-enter | strike | real fill |
|---|---|---|---|---|---|---|
| 2026-05-22 | C @09:45 | long/C @09:45 pullback | True/True | CALLS (allowed=True) | 749 (atm 747) | $-210.0 EXIT_ALL_LEVEL_STOP @prem 1.08 |
| 2026-05-28 | P @09:45 | short/P @09:45 pullback | True/True | PUTS (allowed=True) | 747 (atm 749) | $-132.0 EXIT_ALL_RIBBON_FLIP_BACK @prem 0.59 |
| 2026-05-29 | C @09:45 | long/C @09:45 breakout | True/True | CALLS (allowed=True) | 760 (atm 758) | $-120.0 EXIT_ALL_RIBBON_FLIP_BACK @prem 0.42 |

## Interpretation
- live fired: 3/3 | detector parity: 3/3 | real fills: 3/3
- **WIRED CORRECTLY.** The watcher is registered and fires; the LIVE (Safe-2, enabled=true) heartbeat block would ENTER with the correct side, the per-tier strike, and a real OPRA fill. The zero tracked fills are explained by **no qualifying signal day since the flag went live (< 2 trading days ago)** + Bold inert (no flag), NOT a wiring break.
