# Futures order-path verification — 2026-07-07 (Chef keystone probe)

> SANDBOX/PAPER only. No live money touched. `.env.tastytrade` (gitignored) creds only.

## Keystone: does the Tastytrade order-path reach the broker?

**YES — routes cleanly; a fill is blocked only by sandbox account provisioning, NOT by code.**

### Evidence (quoted from live sandbox runs)

Auth (first call ReadTimeout on cold OAuth refresh @ 10s default; succeeds on retry):
```
CONNECTED sandbox=True account=5WW73759
FRONT MONTH: /MNQU6 exp=2026-09-18
```

Order build + route (real front-month, real DXLink quote bid 29313.25 / ask 29314.0):
```
resting BUY limit @ 27848.25  (5% below mkt, non-marketable)
PLACED id=1203189 status=Routed
POST-PLACE: found=1 status=Rejected
reject_reason= Session offline
```

Dry-run (broker-side validation of the exact order structure):
```
DRY-RUN ok? order= True   warnings= []   bp_effect= True   errors= None
```

Account state:
```
BALANCES net_liq=2000.0 cash=2000.0 futures_bp=0.0
acct type=Individual  margin_or_cash=Margin  futures_account_purpose=None
```

### Diagnosis (root cause, one sentence)
The order builds, prices, and **routes with a valid broker order id** — `dry_run=True` validates it with zero errors and a computed buying-power effect — but the live route is **Rejected with `Session offline`** because the cert account `5WW73759` is **not provisioned for futures** (`futures_account_purpose=None`, `futures_bp=0.0`) and the sandbox futures matching session is not live. This is a **broker/account condition, not a code defect.**

The place → route → poll → cancel → verify-flat plumbing is code-complete and proven up to the routing boundary; end-state was CLEAN (0 positions) every run.

## Notes for whoever wires this next
- SDK `tastytrade` v12.4.1 is installed in **SYSTEM python**, NOT `backtest/.venv`. The adapter/e2e test must run under system python (or add `tastytrade` to the venv).
- The e2e test's static $20,000 fallback price is stale — real MNQ is ~$29,300. Use the DXLink streamer quote (`c.streamer_symbol`) for a real ref price; sandbox REST market-data was 502-ing.
- Cold OAuth refresh can exceed the SDK's 10s httpx default — bump connect timeout on the first call.

---

## 2026-07-07 — DETERMINISTIC FUTURES TICK BUILT (the missing piece)

**VERDICT: FUTURES-TICK-BUILT-DRY-RUN-GREEN** (ready to arm once J provisions futures on 5WW73759).

The order-path was proven above; the ONLY remaining gap was a deterministic tick (the old LLM
futures heartbeat was retired; futures never followed the SPY engine onto `heartbeat_core.py`).
Built to mirror that architecture (arm-flag gating, deterministic see→decide→act, state emit, no LLM):

- `backtest/futures/futures_heartbeat_core.py` — the tick. SEE reuses the VALIDATED
  `run_native_backtest` see-loop (ribbon/VIX/levels/`run_all_watchers`) so the live signal is
  byte-faithful to what v3 was validated on; DECIDE = `should_take_v3` + `risk.size_contracts` +
  `PropAccount.would_violate` kill-switch; ACT = build bracket + deterministic exit plan, place via
  `TastytradeBroker.place_bracket`.
- `backtest/futures/futures_exit_manager.py` — the MISSING exit brain: pure, deterministic,
  stateless-per-call. Mirrors `simulate_futures` doctrine (FULL_STOP pre-TP1 → TP1_PARTIAL + stop→BE
  → RUNNER_TARGET/RUNNER_BE_STOP → TIME_STOP@15:50).
- State emit restored (stale since 06-17): each tick writes `automation/state/futures/{last-tick,
  loop-state,position}.json`.
- Guards: `backtest/tests/test_futures_heartbeat.py` (17, red-proofed).

**ARM GATE (fails safe):** `dry_run = not (FUTURES_ARMED==1 AND futures_bp>0)`. Today `futures_bp=0.0`
on 5WW73759 → even `FUTURES_ARMED=1` stays dry-run and routes nothing (guard-proven).

**Full-chain DRY-RUN proof** (real MNQ bar 2026-06-12 09:35, no mocks): SEE n_signals=2 → DECIDE
took shotgun_scalper short/high @ vix 18.94, sized 1 MNQ (55.5-pt stop × $2 ≈ $111 < $150 budget) →
ORDER built SELL 1 @ 29447 tp1 29306.75 stop 29502.55 routed=false → EXIT plan attached →
action=DRY_RUN_VALIDATED → 3 state files emitted.

**One flip to live-paper:** (1) J enables/provisions futures trading on cert account 5WW73759 so
`futures_bp>0` (broker-side; not a code change); (2) set env `FUTURES_ARMED=1`. Then the SAME tick
routes real sandbox orders. Nothing else changes.
