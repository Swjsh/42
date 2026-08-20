# 🤝 MULTI-SYMBOL LANE — handoff (2026-08-20, pre-open)

> One place to look. Written for J, and for whatever session picks this up next.
> **Nothing is armed. No order was ever placed. The SPY engine is untouched.**

---

## What you asked for, and what exists

**"Copy the entire SPY engine, paste it, don't touch the original, make it trade other names."**

Done. **LANE `multi-symbol` / ARM `multi-1`**, 16 modules under `multi/`, forked from the SPY
engine. Verified at AST level: **zero literal `"SPY"` in executable code**, and the only imports
are `multi.lib.*` + stdlib. The original engine is never imported or modified — its own test
suites still pass.

Every SPY-dollar constant became symbol-relative (ATR-derived for wick/noise tolerances,
percent-of-price for ribbon-spread and the active band — because ATR would perversely *loosen*
during a VIX spike). Pinned by a scale-invariance test: the same chart pattern must score
identically on a $40 stock and a $700 ETF.

## How to look at it

```bash
backtest/.venv/Scripts/python.exe setup/scripts/multi_status.py
```

Open positions with **days held**, capital committed, today's cascade with the **top blocking
gate**, watchlist + relative volume, ledger freshness, and a SHADOW banner.

## How it picks what to trade (the 72-name noise question)

A funnel that narrows by **RANKING at every stage, never thresholding** — because a threshold
can match nothing on a quiet day (L199: *700 signals, 0 trades*) while too-loose is
shotgun-not-sniper. Both failure modes have bitten this shop.

| Stage | Keeps | Ranked on |
|---|---|---|
| universe | ~72 | static membership |
| liquidity | ≤40 | tightest **live** spread |
| attention | ≤15 | **relative volume** + scanner corroboration + news |
| setup | ≤5 | the engine's 0–11 score |
| admission | ≤3 | risk / correlation / sector caps |

Live: 30 symbols → 25 filtered → 5 examined → chain reads on 1. **Relative volume carries stage
2** because it is the only field comparable across an $18 stock and a $700 ETF.

## The account

**PA38EG1JTFBT** — highest paper balance ($9,628), options level 3. Credentials resolve **by
reference** from the crypto twin's existing secrets; no secret was copied into a second file, and
`verify_account()` refuses to run if the key authenticates as a different account.

⚠️ **Shared with the armed crypto twin.** Enforced in code, not just noted: every position read
filters to OCC-shaped equity options, so this lane cannot see or close the twin's BTC, and the
twin cannot touch these options. **Account equity is therefore NOT evidence for either program** —
each reads its own ledger. The status surface is guarded so equity can never be shown as lane P&L.

## Six bugs found by RUNNING it, not reading it

1. **Levels gap** — filter 10 required a level-tied trigger; none were passed. Vetoed **100% of
   symbols forever** while reading as "no setups today." Found by the participation cascade.
2. **Bootstrap trap** — position state correctly refuses to treat a missing file as "no open
   positions," but unbootstrapped it logged a BLOCKED row every tick, noise that would mask a
   real alarm.
3. **Fake gate in the analytics** — the status surface chained a universe-wide counter between
   funnel stages, inventing a phantom "dropped 35" bottleneck.
4. **Equity-as-P&L leak** — caught by a guard that RED-proofs by showing $9,628.45 bleeding into
   the P&L line.
5. **Scanners feeding nothing** — they ran and wrote JSON while `scanner_hits` stayed 0.
6. **Two Alpaca data bugs** — a missing `start` returned ZERO bars on every feed; missing
   pagination silently capped history at ~1 month (192 → 1,505 bars once fixed).

## ⚠️ What is NOT proven

**No name has cleared the liquidity gate.** The market is closed, options do not quote, and every
attempt returns `no two-sided quote` — the gate refusing rather than fabricating a mid.
Everything upstream works on live data and selects real contracts (XLF 57.5P, SLV 60C,
NVDA 217.5P at 4 DTE).

**Whether real RTH quotes produce a `WOULD_PLACE` row is genuinely unknown** until
`Gamma_MultiCore` fires at **09:35 ET**. That task is registered, verified, and proven to run
headless *by written artifact* — not merely registered. The cascade names the blocking gate every
tick, so a zero-participation morning is explained in one read.

## Not mine, but you should know

**A graduated safety guard is DEAD in full-suite runs.**
`test_graduated_guards.py::test_free_model_cost_estimate_is_zero` fails in a full run, passes
alone — it guards a real scar (phantom cost from `:free` slugs corrupting spend summaries).
Bisected to a 2-file repro; **not fully root-caused** (the error is deeper than the sys.modules
shadowing I diagnosed), and my fix attempt **failed and was reverted** rather than left
half-applied. It is **invisible to the pre-commit gate**. Full writeup:
`strategy/candidates/_lesson-inbox/graduated-guard-dead-in-full-suite-2026-08-20.md`.

## Where things live

- Doctrine + status: `markdown/planning/WEEKLY-OPTIONS-PROGRAM.md` §9a (status), §9c
  (classification / awareness / funnel)
- Soul file: one `CLAUDE.md` tech-stack row · full entry in `CHANGELOG.md`
- Config: `automation/state/multi/params.json` (tracked); live state beside it (gitignored)
- Code: `multi/` (16 modules) · `setup/scripts/multi_status.py` · `multi_scanner_run.py`
- Tests: `backtest/tests/test_multi_*.py` — 301+, guards RED-proofed
- Ledgers: `automation/state/multi/{shadow-ledger,participation-cascade}.jsonl`,
  `journal/trades-multi.csv`

## The one thing that needs you

Nothing, before the open. When a signal eventually clears every gate and you want it to place
real paper orders, that is a deliberate change from `shadow_only: true` — not a flag I flip
unattended. **Live money remains yours alone (OP-0 #1).**
