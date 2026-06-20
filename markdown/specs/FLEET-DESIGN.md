# Champion / Challenger Fleet — Design

> Run several frozen configs in parallel so we collect multiple statistically-valid
> baselines at once — without freezing the firm or stopping the kitchen. Each account/arm
> holds ONE config frozen; the PORTFOLIO of arms keeps evolving. Replaces the "freeze for a
> month" plan (J, 2026-06-20). Baseline to beat: [HONEST-PNL-BASELINE-2026-06-20](../analysis/HONEST-PNL-BASELINE-2026-06-20.md).

## Why this dissolves the freeze tension

"You can't measure edge in a ruleset you keep changing" is true **per account**, not per firm.
Hold each config frozen *inside its own arm*; let new configs spin up as *new* arms. The kitchen
becomes a **feeder** of challengers instead of an accumulator of untriaged candidates (Rule 22).

## Core mechanic: one perception, many policies

Never run N LLM heartbeats (N× cost). Instead:

1. **One heartbeat** computes the chart read / levels / score **once per tick** → writes
   `automation/state/fleet/shared-signal.json`.
2. A deterministic **fleet executor** (pure Python, $0) reads that signal and fans it out to
   every active arm. Each arm applies its **frozen** gate + sizing + instrument and routes an
   order to its bound broker.

Cost ≈ flat regardless of arm count: 1 perception + N cheap gate-evals. Each arm's gate must be
expressible as **config/code**, not an LLM judgment (most of v15 already is: scores, thresholds).

## Two fidelity tiers (the honest constraint)

Real fills are the only WR authority (lesson theme C1); BS-sim is ranking-only.

| Tier | Count | Fidelity | Role |
|---|---|---|---|
| **Real paper** | scarce (~3 Alpaca cap/login) | real fills + spread | the ONLY arms that settle "is it profitable" |
| **Shadow overlay** | unlimited, $0 | re-scores the SAME real signal under a different gate | measures "would config X have done better" on real fills, no extra account |
| **Virtual sim** | unlimited, $0 | BS-sim | screen kitchen candidates; cannot crown a winner |

Spend the scarce real accounts on the hypotheses whose fill-fidelity matters most. The **A+ arm
needs no account** — it runs as a shadow overlay on the existing real accounts.

## Graduation pipeline (kitchen → live)

```
kitchen candidate → backtest gate → virtual sim arm → beats baseline in sim
   → promote to shadow overlay / real paper slot → accrues real-fill record
   → beats frozen baseline over N≥30 clean trades → live candidate
underperformers retire; their slot/lane recycles for the next challenger
```

## Promotion gate (reuse eval-first doctrine, OP-11/OP-22)

`oos_positive AND wf ≥ 0.70 AND sub_window_stable AND anchor_no_regression AND clean_trades ≥ 30`
AND beats the frozen baseline by a margin that survives multiple-comparison correction.

## Two gotchas designed around

1. **Arms must diverge in what they actually trade** (different strike / gate / instrument). Two
   arms placing the identical order = one data point, not two.
2. **Winner's curse.** N arms + pick-best = luck-mining. Pre-register each arm's hypothesis;
   require the margin above + fresh-OOS confirmation before promotion.

## Provisioning (cheap)

Fleet executor places via **REST using per-account keys referenced in
`automation/state/fleet/accounts.json`** (key_ref pointers — NEVER secrets in git). MCP servers
stay wired only for the 1–2 accounts watched interactively, to keep context lean.

## Starting fleet

See `automation/state/fleet/accounts.json`. Runs TODAY with zero new accounts: Safe + Bold as
real-fill champions, A+ as a shadow overlay on them, MES as a futures-sim arm. New real Alpaca
slot is a fidelity *upgrade* for the best challenger, not a prerequisite.
