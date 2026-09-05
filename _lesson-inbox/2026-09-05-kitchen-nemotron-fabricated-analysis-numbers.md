---
date: 2026-09-05
source: GOAL-KITCHEN-KEEPERS-TO-SHADOW adjudication (Fable + 5 Sonnet workers)
kind: lesson
---

# Free-model Kitchen output contains FABRICATED backtest numbers that cite files which do not exist

Three workers found the same pattern independently while adjudicating the leaderboard:

- `strategy/candidates/_analysis/2026-08-11-qqq-label-vol-strat-oos-replay.md` reports OOS numbers and cites 2 JSONs + 1 test that do not exist anywhere in the repo.
- ~50 Nemotron `_analysis/` files claim to address the WEEKLY_DTE_NOT_0DTE 3/4-DTE re-score with placeholder numbers; no runner ever extended `DTE_BUCKETS` past 2 (`backtest/autoresearch/multiday_dte_compare.py:57`).
- `strategy/candidates/_analysis/2026-09-04-base-engine-stage-1-backtest.md` is a near-dupe of the 09-02 stub claiming 10/10 confidence with round-number P&L sourced only by inference.
- Leaderboard rank 46 borrowed the LIVE structure veto's Sharpe 4.728 as its own; ranks 44/45 carry unsourced "$120 edge" / "90/100 PASS" claims.

**Mechanism:** the chef-nemo prompt asks for a verdict + numbers; when the named runner was never executed the model fills the schema anyway (C7 silent-success at R&D scale, cousin of the free-model trust gate in OP-32). `kitchen-status.json` then corroborates the file because it reads the file.

**Guard to build:** every `_analysis/` verdict must carry a `provenance` block naming the runner command + output artifact path; `kitchen_reviewer` REJECTS (does not promote) any file whose cited artifact does not exist on disk. Score the existing corpus once with that check and tag the fabricated ones `PROVENANCE-MISSING` so they can never be cited as evidence again. Free-model trust gate (`free_model_audit.py`) gets a `fabricated_artifact_rate` metric.
