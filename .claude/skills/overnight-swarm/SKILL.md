---
name: overnight-swarm
description: Nightly backtest swarm that scores the full candidate matrix and writes a ranked morning shortlist (analysis/overnight-shortlist-{date}.md). Ranks per OP-16 (edge x daily-Sharpe), regression-gates each variant vs its same-strike baseline (compare.py's $50/day rule), and flags only RATIFY-READY variants (flat-or-better every day + positive total). Pure-Python, $0, never auto-deploys. Use overnight, or when J asks "what came out of the backtests" / "any candidates worth ratifying".
---

# Skill: overnight-swarm

Turns the 80+ standing sweep scripts into ONE ranked shortlist J reads each morning. The `/insights` report (2026-06-18) found the sweeps existed but nothing aggregated them into a decision surface - this closes that gap.

> Per OP-16: the shortlist is J's **REVOKE** surface, not an auto-deploy. Nothing here touches `params.json`, `heartbeat.md`, or live orders. Per LESSONS C4: never declare improvement on a single good day - a variant must be flat-or-better on EVERY day to be ratify-ready.

---

## When to invoke

- **Overnight**, after the backtest matrix has run (wire into `gamma-overnight-grinder` STAGE 1, or its own nightly task).
- **On demand** when J asks "what came out of the backtests?" / "anything ratify-ready?".

---

## Steps

1. **Consume the latest matrix results** (fast, no re-run):

```bash
cd C:/Users/jackw/Desktop/42/backtest
python -m autoresearch.overnight_swarm --top 10
```

2. **Refresh the pool first, then rank** (slower - re-runs `tools/run_all_sniper.py`):

```bash
python -m autoresearch.overnight_swarm --run --top 10
```

3. **Read the shortlist:**

```bash
cat analysis/overnight-shortlist-$(date +%Y-%m-%d).md
```

---

## Output

| File | What |
|------|------|
| `analysis/overnight-shortlist-{date}.md` | Human-readable ranked table + RATIFY-READY section |
| `analysis/overnight-shortlist-{date}.json` | Structured: per-candidate score, sharpe, gate verdict, per-day P&L |
| `automation/overnight/STATUS.md` | One-line pointer appended (signal, not silence - OP-25) |

### Gate verdicts

| Gate | Meaning |
|------|---------|
| `RATIFY_READY` | Variant is flat-or-better than its baseline on every shared day AND total > 0. The only deploy-worthy class. |
| `REGRESSED` | Lost > $50 on at least one day vs baseline. Rejected (detail lists the days). |
| `FLAT_BUT_UNPROFITABLE` | No regression but total <= 0. Not worth deploying. |
| `BASELINE` | This row IS the current strategy, not a proposed change. |
| `NO_BASELINE` | No same-strike `V0_baseline` to compare against. |

**Ranking metric:** `total_pnl x daily_sharpe` (OP-16 edge x sharpe). Negative-total candidates rank last.

---

## What this skill NEVER does

- Modify `params.json` / `heartbeat.md` / any doctrine (Rule 9 / OP-16).
- Place orders or call any broker MCP.
- Auto-ratify. A RATIFY-READY flag is an *invitation for J to review*, gated further by the Karpathy eval-first stack (OOS positive + WF >= 0.70 + sub-window stable + anchor no-regression + A/B scorecard) before anything ships.

---

## Cross-references

- **Tool source:** `backtest/autoresearch/overnight_swarm.py`
- **Backtest matrix:** `backtest/tools/run_all_sniper.py` (real fills, OOS + anchor gate)
- **Regression gate semantics:** `backtest/tools/compare.py` ($50/day threshold)
- **Ranking doctrine:** CLAUDE.md OP-16 (J-edge / edge_capture x sharpe)
- **Consumed by:** `gamma-overnight-grinder` wake protocol; J's morning brief.
