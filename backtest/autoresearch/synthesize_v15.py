"""Synthesize the v15 ratification recommendation.

Reads all available evidence:
  1. All random_eval batches (A-F, 60 seeds)
  2. Sub-window stability results (sub_window_seed*.json)
  3. Seed-climb hill-climbing state (seed{N}_climb/state.json + history.jsonl)

Writes:
  - analysis/recommendations/v15.json -- the ratification scorecard
  - analysis/weekend-research-findings.md -- updated synthesis section

Decision logic:
  candidate_pool = robust seeds (pos train sharpe + pos val pnl + n_val >= 25)
                 + best post-climb state per starting seed
  winner = candidate with highest robust_score AND sub_window_stable
           (positive PnL on >= 3 of 5 sub-windows)
  if winner exists: verdict = ratify v15 with winner's params
  else:             verdict = needs_review (no candidate cleared all gates)

CLI:
  python -m autoresearch.synthesize_v15
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoresearch import config
from autoresearch.aggregate_random import collect_all_results, rank_robust

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parent.parent
SEARCH_DIR = REPO / "autoresearch" / "_state" / "random_search"
STATE_DIR = REPO / "autoresearch" / "_state"
ANALYSIS_DIR = REPO.parent / "analysis"
RECOMMENDATIONS_DIR = ANALYSIS_DIR / "recommendations"


def load_sub_window_results() -> dict[int, dict[str, Any]]:
    """Read all sub_window_seed*.json files. Returns {seed: result_dict}."""
    out: dict[int, dict[str, Any]] = {}
    if not SEARCH_DIR.exists():
        return out
    for path in sorted(SEARCH_DIR.glob("sub_window_seed*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            seed = data.get("seed")
            if isinstance(seed, int):
                out[seed] = data
        except json.JSONDecodeError:
            continue
    return out


def load_climb_states() -> dict[int, dict[str, Any]]:
    """Read all _state/seed{N}_climb/state.json files. Returns {seed: state_dict}."""
    out: dict[int, dict[str, Any]] = {}
    if not STATE_DIR.exists():
        return out
    for d in sorted(STATE_DIR.glob("seed*_climb")):
        # parse seed number from directory name
        try:
            seed_str = d.name.replace("seed", "").replace("_climb", "")
            seed = int(seed_str)
        except ValueError:
            continue
        state_path = d / "state.json"
        if not state_path.exists():
            continue
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            out[seed] = data
        except json.JSONDecodeError:
            continue
    return out


def is_sub_window_stable(sub_window_data: dict[str, Any]) -> bool:
    """Return True if the candidate has positive PnL AND positive Sharpe on >= 3 of 5."""
    if not sub_window_data:
        return False
    stability = sub_window_data.get("stability", {})
    return bool(stability.get("is_robust", False))


def build_candidate_pool(
    random_records: list[dict[str, Any]],
    sub_windows: dict[int, dict[str, Any]],
    climb_states: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Assemble unified candidate pool from all evidence sources."""
    pool: list[dict[str, Any]] = []

    # 1. Random search candidates (already ranked)
    for r in random_records:
        seed = r.get("seed")
        sub = sub_windows.get(seed) if isinstance(seed, int) else None
        is_stable = is_sub_window_stable(sub) if sub else None
        pool.append({
            "source": "random_eval",
            "seed": seed,
            "params": r.get("params"),
            "train_metrics": r.get("train_metrics"),
            "validate_metrics": r.get("validate_metrics"),
            "robust_score": r.get("robust_score"),
            "sub_window_stable": is_stable,
            "sub_window_summary": sub.get("stability") if sub else None,
        })

    # 2. Post-climb candidates — only include if hill-climb produced a different
    #    set of params (i.e., at least one KEEP iteration after the seed start).
    for seed, st in climb_states.items():
        if st.get("modifications_kept", 0) > 0:
            sub = sub_windows.get(seed)
            is_stable = is_sub_window_stable(sub) if sub else None
            pool.append({
                "source": "seed_climb",
                "seed": seed,
                "starting_params": "see seed_climb baseline",
                "params": st.get("current_params"),
                "train_metrics": st.get("baseline_metrics"),
                "validate_metrics": st.get("validate_baseline_metrics"),
                "iterations_kept": st.get("modifications_kept"),
                "iterations_total": st.get("iteration"),
                "sub_window_stable": is_stable,
                "sub_window_summary": sub.get("stability") if sub else None,
            })

    return pool


def pick_winner(pool: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Apply the v15 ratification gates and return the best surviving candidate.

    Gates:
      1. positive train_sharpe AND positive validate total_pnl
      2. validate n_trades >= 25
      3. sub_window_stable == True
      4. robust_score > 0

    Among survivors, return the one with the highest robust_score (or
    fallback to validate_pnl if score is missing).
    """
    survivors: list[dict[str, Any]] = []
    for c in pool:
        tm = c.get("train_metrics") or {}
        vm = c.get("validate_metrics") or {}
        train_sh = float(tm.get("sharpe_daily", 0))
        val_pnl = float(vm.get("total_pnl", 0))
        n_val = int(vm.get("n_trades", 0))

        passes_sharpe = train_sh > 0
        passes_pnl = val_pnl > 0
        passes_trade_count = n_val >= 25
        passes_stability = bool(c.get("sub_window_stable"))
        passes_score = float(c.get("robust_score") or 0) > 0

        if all([passes_sharpe, passes_pnl, passes_trade_count, passes_stability, passes_score]):
            survivors.append(c)

    if not survivors:
        return None

    survivors.sort(key=lambda c: (
        float(c.get("robust_score") or 0),
        float(c.get("validate_metrics", {}).get("total_pnl") or 0),
    ), reverse=True)
    return survivors[0]


def build_scorecard(
    winner: dict[str, Any] | None,
    pool: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the v15.json ratification scorecard."""
    n_robust = sum(
        1 for c in pool
        if (c.get("train_metrics") or {}).get("sharpe_daily", 0) > 0
        and (c.get("validate_metrics") or {}).get("total_pnl", 0) > 0
    )
    n_stable = sum(1 for c in pool if c.get("sub_window_stable") is True)

    if winner is None:
        verdict = "needs_review"
        reason = "no candidate cleared all 4 gates (train_sharpe>0, val_pnl>0, n_val>=25, sub_window_stable)"
    else:
        verdict = "auto_ratify_recommend"
        reason = f"seed={winner['seed']} from {winner['source']} cleared all gates"

    return {
        "rule_id": "v15",
        "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "verdict": verdict,
        "reason": reason,
        "winner": winner,
        "candidate_pool_size": len(pool),
        "n_robust_candidates": n_robust,
        "n_sub_window_stable": n_stable,
        "evidence": {
            "random_seeds_evaluated": sum(1 for c in pool if c["source"] == "random_eval"),
            "climb_starting_seeds": sum(1 for c in pool if c["source"] == "seed_climb"),
        },
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    logger.info("loading random_eval results...")
    random_records = collect_all_results()
    if not random_records:
        logger.error("no random_eval results found — run random_eval first")
        return 1
    ranked = rank_robust(random_records)
    logger.info("loaded %d random_eval records", len(ranked))

    logger.info("loading sub_window stability results...")
    sub_windows = load_sub_window_results()
    logger.info("loaded sub_window for seeds: %s", sorted(sub_windows.keys()))

    logger.info("loading hill-climb states...")
    climb_states = load_climb_states()
    logger.info("loaded climb states for seeds: %s", sorted(climb_states.keys()))

    pool = build_candidate_pool(ranked, sub_windows, climb_states)
    logger.info("candidate pool size: %d", len(pool))

    winner = pick_winner(pool)
    scorecard = build_scorecard(winner, pool)

    RECOMMENDATIONS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RECOMMENDATIONS_DIR / "v15.json"
    out_path.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")

    print()
    print("=" * 70)
    print("V15 RATIFICATION SCORECARD")
    print("=" * 70)
    print(f"Verdict:                {scorecard['verdict']}")
    print(f"Reason:                 {scorecard['reason']}")
    print(f"Candidate pool:         {scorecard['candidate_pool_size']}")
    print(f"Robust candidates:      {scorecard['n_robust_candidates']}")
    print(f"Sub-window stable:      {scorecard['n_sub_window_stable']}")
    if winner:
        vm = winner["validate_metrics"]
        tm = winner["train_metrics"]
        print()
        print(f"WINNER: seed={winner['seed']} (source={winner['source']})")
        print(f"  Train PnL:          ${tm.get('total_pnl', 0):+.0f}")
        print(f"  Train Sharpe:       {tm.get('sharpe_daily', 0):+.3f}")
        print(f"  Train trades:       {tm.get('n_trades', 0)}")
        print(f"  Validate PnL:       ${vm.get('total_pnl', 0):+.0f}")
        print(f"  Validate Sharpe:    {vm.get('sharpe_daily', 0):+.3f}")
        print(f"  Validate trades:    {vm.get('n_trades', 0)}")
        print(f"  Robust score:       {winner.get('robust_score', 0)}")
    print()
    print(f"Scorecard written to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
