# Kalshi lane — what's built, and the 4 steps to arm it

> **Built 2026-08-09.** Status: **SHADOW, wired, 18/18 tests green.** No credentials present,
> no orders placed, no money moved. Seed account: **$10**.

---

## What exists

| File | Role |
|---|---|
| [`automation/kalshi/kalshi_client.py`](../../automation/kalshi/kalshi_client.py) | REST client — RSA-PSS auth, market data, **orderbook depth**, limit orders |
| [`automation/kalshi/kalshi_signal_map.py`](../../automation/kalshi/kalshi_signal_map.py) | Ports `shared-signal.json` → a Kalshi index contract |
| [`automation/kalshi/kalshi_tick.py`](../../automation/kalshi/kalshi_tick.py) | One tick: decide → log → (if armed) place |
| [`automation/kalshi/params.json`](../../automation/kalshi/params.json) | Every knob. No hardcoded values in code. |
| [`automation/kalshi/test_kalshi_lane.py`](../../automation/kalshi/test_kalshi_lane.py) | 18 guards |
| [`setup/scripts/run-kalshi-tick.ps1`](../../setup/scripts/run-kalshi-tick.ps1) | Scheduled-task wrapper, **arm line commented out** |
| `automation/state/kalshi/shadow-ledger.jsonl` | Append-only evidence — every tick, traded or not |

---

## The safety posture

A live order requires **BOTH**, and there is no third path:

1. `GAMMA_KALSHI_ARMED=1` in the environment, **and**
2. credentials present in the gitignored secrets store.

Missing either → shadow. Additionally:

- **Maker only.** The client exposes *no market-order call at all* — a guard test asserts
  `"type": "market"` appears nowhere. Taking the spread costs 5–6× the maker fee.
- **Fails closed** on entries: stale signal, unreadable position list, or any market-data error
  → no trade. Reads fail open.
- **Every tick is logged**, including no-trades. A silent skip destroys auditability.
- Gates: max 5¢ spread · min 50 contracts depth · price band 0.35–0.65 · score ≥ 6 ·
  1 concurrent position · $8 max stake · **$3 daily loss cap** (−30%, mirroring Safe doctrine).

---

## The mapping — how a SPY decision becomes a Kalshi trade

Gamma trades **SPY**; Kalshi lists the **S&P 500 index** (~10× SPY). **We never convert.**
Hardcoding a 10.0× ratio would go stale the first time dividends or a data seam moved it.

Instead the ladder **self-calibrates**: the strike whose YES price sits nearest 0.50 *is* the
market-implied level, so selection is relative to the market's own quotes. Nothing to drift.

- `ENTER_BULL` → buy **YES**
- `ENTER_BEAR` → buy **NO** *(same contract, other side — never a separate ladder)*
- `HOLD` / score < 6 → no trade

`production_action` is authoritative — we deliberately do **not** re-derive direction from raw
scores. Two engines disagreeing about the same tick is a drift bug this project has already paid for.

**Verified end-to-end** against live market data with synthetic signals:
```
BULL  -> KXBTCD-26AUG1417-T64999.99 YES x15 @52c  stake $7.80  fee $0.07  breakeven 52.47%
BEAR  -> KXBTCD-26AUG1417-T64999.99 NO  x17 @46c  stake $7.82  fee $0.08  breakeven 46.47%
weak score 3 -> refused at the score gate
index series -> correctly blocked (34c weekend spreads > 5c gate)
```

---

## 🔴 The 4 steps to arm — only you can do steps 1–2

### 1. Generate an API key on Kalshi
Account → **API Keys** → create. You get a **Key ID** (UUID) and download an **RSA private key**
(`.pem`). **The private key is shown once.** I never see it and cannot create it for you.

### 2. Drop the credentials in the gitignored store
Save the `.pem` — `*.pem` is already gitignored (`.gitignore:47`):
```
automation/state/fleet/kalshi-1.pem
```
Then add this block to `automation/state/fleet/secrets.json` under `accounts` (that file is
gitignored at `.gitignore:74`):
```json
"kalshi-1": {
  "key": "<YOUR-KEY-ID-UUID>",
  "secret_path": "automation/state/fleet/kalshi-1.pem",
  "base_url": "https://api.elections.kalshi.com/trade-api/v2",
  "label": "KALSHI-1"
}
```
> Never paste the key into chat, a tracked file, or a commit. `secret_path` is preferred over
> inlining the PEM — it keeps multi-line key material out of JSON entirely.

### 3. Verify
```bash
python automation/kalshi/kalshi_tick.py --status
```
Expect `credentials = LOADED (KALSHI-1)` and `balance = $10.00`. If balance reads but
positions error, the key lacks trading permission.

### 4. Arm (only when you decide to)
Uncomment the arm line in [`run-kalshi-tick.ps1`](../../setup/scripts/run-kalshi-tick.ps1), or for
a one-off:
```bash
GAMMA_KALSHI_ARMED=1 python automation/kalshi/kalshi_tick.py
```
**REVOKE** = re-comment the line, or disable the task. Nothing else needs touching.

---

## 🚨 The open risk to this plan

The S&P series you want to trade (`KXINXU`, `KXINX`) were the **worst books in the survey** —
**34–36¢ spreads on 9–46 contracts**, versus 1¢ on 858–1,701 for NFL. At those spreads the 5¢
gate blocks every trade, correctly.

**That is a Sunday reading with equities closed**, so it is not yet a verdict — market makers pull
quotes off-hours. **The RTH re-run settles it**, and it costs nothing:
```bash
python research/kalshi/kalshi_liquidity_survey.py
```
If index spreads stay wide during RTH, the lane will sit at zero trades. Two honest options then:
retarget the port at a series that *is* liquid (BTC daily ranges were 1–2¢ with 200–2,300 depth,
and are 24/7), or accept the lane is index-blocked and say so.

---

## Not yet done

- **Scheduled task not registered.** The wrapper is tested and ready; registering it also means
  updating `automation/state/SCHEDULED-TASKS.md`. Worth doing once the RTH spread question is
  settled — a task that logs "blocked, 34¢ spread" every 5 minutes is noise.
- **Exit logic.** The lane currently only ENTERS. Kalshi contracts settle themselves at $0/$1, so
  holding to settlement is valid (and is the *cheap* path — no exit fee). But there is no
  early-exit/stop path yet. **Decide this before arming**, not after.
- **Fill-rate evidence.** The whole maker-only thesis rests on resting orders actually getting
  filled. Unknown until real orders rest on a real book.
