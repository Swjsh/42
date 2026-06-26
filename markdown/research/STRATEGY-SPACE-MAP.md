# Strategy-Space Map — the combinatorial grid we systematically cross off

> J 2026-06-24: "we have 6 accounts and an almost infinite amount of strategy possibilities with gates and conditions... why are we not mapping this infinite amount of possibilities and crossing them off as we learn to improve the system."
>
> The answer to "infinite": you don't brute-force it — you **stage a frontier search per dimension**, hold the rest at the current best, keep the knee, cross off the dead regions in a ledger so they're never re-tested, and promote survivors to the 6 live-paper accounts. This file is the dimension map; the ledger is `analysis/backtests/STRATEGY-SPACE-REGISTRY.jsonl`.

## The dimensions (the knobs)

| # | Dimension | Values | Expressible today? |
|---|---|---|---|
| **D1** | **Contract structure** (*what* we trade) | 0DTE-single · 1DTE-single · 0DTE debit-vertical · credit-spread · calendar | 0DTE-single ✅ · rest needs **simulator work** (the option-tax dimension — see risky-3) |
| **D2** | **Strike / contract price** | OTM-3 · OTM-2 · OTM-1 · ATM · ITM-1 · ITM-2 (per equity tier) | ✅ `strike_offset` / `v15_strike_offset_per_tier` |
| **D3** | **Sizing** | qty tiers (base/elite × equity) · `risk_cap_pct` · `min_contracts` | ✅ `position_sizing_tiers` |
| **D4** | **Direction** | calls · puts · both · `direction_lock` | ✅ post-filter |
| **D5** | **Gates / conditions** | `block_level_rejection` · morning-block · VIX caps · `min_triggers` · score threshold · `ribbon_spread_min_cents` · regime gates | ✅ `params_overrides` |
| **D6** | **Exit** | stop type (chart / premium-% / dollar) × value · TP1 % + qty-fraction · runner target · chandelier trail · **HTF target-cap** · time stop | ✅ mostly (HTF-cap = new, Plan 2) |
| **D7** | **Entry regime** | trend vs chop · VIX *character* · HTF-zone alignment · time-of-day | partial (HTF/regime = Plan 2/3 builds) |

The space = D1×D2×…×D7. "Infinite" only if brute-forced. We grind it staged.

## The grind method (cheap → live)

1. **Backtest tier (real OPRA fills, $0):** staged frontier — fix all dims at the current best, sweep ONE dim, keep the knee (loosest still +EV, like the gate sweep found `block_level_rejection`), record EVERY combo to the registry with a verdict. Cross-validate the top combos for interactions. Driver = extend `gate_frequency_frontier.py` to D2/D3/D5/D6.
2. **Live-paper tier (the 6 accounts):** the top backtest survivors run as frozen challengers. **The 3 safe accounts** stay disciplined (control / A+ tight / a validated looser). **The 3 risky accounts run wide-open** (J: "remove as many gates as you want on the risky accounts") — the loose/loosest configs the backtest can't bless under OP-16 but that we *want live-paper evidence* on. $0 risk, real fills.
3. **Cross off:** anything DEAD on real fills → `verdict: DEAD` in the registry, never re-tested. Anything `PROMOTE` clears OP-16 → ships. `CHALLENGER` = run live-paper. `HOLD` = +EV but below OP-16 floor (PROPOSE).

## Agent efficiency (J directive 2026-06-24 — don't burn Sonnet on mechanical runs)

The backtest IS pure Python (`$0`, no LLM). The only LLM cost is the agent that launches the script + parses JSON. So:

- **One script, not N agents.** A full grid (e.g. 36 strike×gate×stop cells) runs **in-process in ONE Python script** (`strategy_space_grind.py`). Do NOT fan out one LLM agent per cell.
- **Cheap runner, smart synth.** The grind workflow = **1 agent on `model:'haiku'` + `effort:'low'`** to run the script + return its JSON, then **1 synthesis agent** (Sonnet) to rank + register. Reserve Sonnet/Opus for synthesis + adversarial verify ONLY — never for "run this command, read the number."
- **Cost delta:** that turns a ~8-Sonnet-agent grind into ~1 Haiku + 1 Sonnet. Per OP-3 + [[feedback_efficiency_at_every_step]] + [[feedback_free_swarm_only]] ($0 research). The 6 accounts are the live-paper tier — also $0 (paper fills), no LLM per fill (the fleet executor is pure Python).

## Verdict ladder (registry `verdict` field)
`PROMOTE` (clears OP-16, auto-ship) · `HOLD` (+EV, < OP-16 771 floor → PROPOSE) · `CHALLENGER` (run on a paper account) · `CROSSED_OFF` (tested, not worth pursuing) · `DEAD` (real-fills negative / null-reproducible).

## Status
Framework shipped 2026-06-24. Registry seeded with everything learned to date (the ~64 dead families, the gate-sweep L2/L3/L4, Plan-3 dead inputs, the live edges). First multi-dimensional grind (D2 strike × D3 sizing × D5 gate-frontier) launched. Structure (D1) expansion + HTF-cap (D6) are the next dimensions once their builds land.
