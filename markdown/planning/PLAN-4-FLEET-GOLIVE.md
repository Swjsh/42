# Plan 4 — 6-Account Fleet Go-Live (infra finalization)

> The concrete infra to make the differentiated fleet actually scalp. Most is built + tested (22/22) as of 2026-06-24; this tracks what remains.

## Done (2026-06-24)
- Per-arm sizing override built in `fleet_executor._params_for` (real lever = `params_patch` → position_sizing_tiers/strike, NOT the inert min_contracts). Parity-tested.
- 6 differentiated arm configs wired in `accounts.json` (5 real + `safe-loose` pending).
- Keystone producer fix (`passed_scoring_peak` + dual-perception `build()`) behind `SCORING_PEAK_LIVE` flag (default OFF = byte-identical v1). Proven to catch today's 5 gated reclaim signals, 0 over-emission.
- **All 6 distinct Alpaca accounts wired + broker-verified (2026-06-24).** J supplied the safe-side keys; `validate_keys.py` confirmed 6 unique account numbers (SAFE-2 gap closed). Re-mapped: `safe-1`=PA3DHPT7KIQE (loose, fleet_rest, **new account**) / `safe-2`=PA3S2PYAS2WQ (control, mcp_heartbeat = the production Gamma-Safe-2 account — stays on the heartbeat path, NOT fleet_rest, so no double-trade) / `safe-3`=PA32RD49OB0Q (A+ tight) / `bold-2`,`risky-1`,`risky-3` unchanged. Integrity check: every arm's `account_number` matches its key's broker account. Tests 22/22, dry tick clean.

## Remaining
1. **Fix 2 arms** flagged by the verify phase: `safe-3` mis-sized (fires qty8 at $2K, exceeds its cap — needs a `params_patch` to size down) and `bold-2` doc mismatch (behavior fine, text wrong).
2. **Live producer flip** — set `SCORING_PEAK_LIVE = True` (or pass `scoring_peak=True` from the wrapper). After-close only; gated on tests staying 22/22 + a `fleet_live.py --quiet` (no `--live`) WATCH eyeball. Takes effect next RTH. Rollback = flag off (byte-identical).
3. **Feed back Plan 1's sweet-spot** into each fleet_rest arm's `gate_override` once the backtest ranks the looseness levels.

> 6th-account gap **CLOSED 2026-06-24** — all 6 accounts now exist + wired (see Done). The earlier "only 5" was a dead `safe-1` key; J's correct key maps to a genuinely separate account (PA3DHPT7KIQE).

## Owner / status
Gamma (me). Items 1–2 next (after-close: safe-3 sizing fix + producer flip); item 3 waits on Plan 1's backtest. All 6 accounts active + validated; `safe-1`/`risky-3` (loose) held `live:false` until the flip + a Monday-RTH validation order.
