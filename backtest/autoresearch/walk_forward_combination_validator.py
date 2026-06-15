"""Walk-forward validation for combination_search results.

Splits the data into a train window and a test (OOS) window, runs the
combination_search on each, and reports WR stability for each combo.

Usage:
    python backtest/autoresearch/walk_forward_combination_validator.py \
        --csv backtest/data/spy_5m_2025-01-01_2026-05-15.csv \
        --vix-csv backtest/data/vix_5m_2025-01-01_2026-05-15.csv \
        --train-end 2025-09-30 \
        --test-start 2025-10-01 \
        --test-end 2026-05-15 \
        --top-combos "momentum_acceleration|regime=ALIGNED|vix=HIGH_VOL" \
                     "double_bottom|prox=NOT_NEAR_NAMED|time=MORNING|vix=LOW_VOL"

Output: analysis/walk-forward-combination-{date}.{json,md}
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _run_search(csv: str, vix_csv: str, start: str, end: str,
                min_n: int = 15, wr_floor: float = 50.0) -> dict:
    """Run combination_search.py for the given date window and return the JSON output."""
    script = ROOT / "backtest" / "autoresearch" / "combination_search.py"
    out_dir = ROOT / "analysis" / "_wf_tmp"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, str(script),
        "--range", start, end,
        "--csv", csv,
        "--vix-csv", vix_csv,
        "--min-n", str(min_n),
        "--wr-floor", str(wr_floor),
        "--top-n", "500",   # get all passing combos, not just top 20
        "--output-dir", str(out_dir),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT),
                           creationflags=_CREATE_NO_WINDOW)
    if result.returncode != 0:
        print(f"[wf-validator] combination_search failed:\n{result.stderr}", file=sys.stderr)
        return {}

    json_files = sorted(out_dir.glob("combination-search-*.json"), key=lambda p: p.stat().st_mtime)
    if not json_files:
        print("[wf-validator] no output JSON found", file=sys.stderr)
        return {}
    with open(json_files[-1]) as f:
        return json.load(f)


def _find_combo(search_result: dict, combo_label: str) -> dict | None:
    """Find a specific combo (by partial label match) in the search result."""
    for combo in search_result.get("top_passing", []):
        if combo_label in combo.get("label", ""):
            return combo
    return None


def _normalize_label(label: str) -> str:
    """Normalize a combo label: strip spaces around | separators."""
    return "|".join(part.strip() for part in label.split("|"))


def _find_combo_anywhere(search_result: dict, combo_label: str) -> dict | None:
    """Search top_passing + top_failing_by_score for a combo (exact label match after normalization)."""
    sources = list(search_result.get("top_passing", []))
    sources += list(search_result.get("top_failing_by_score", []))
    needle = _normalize_label(combo_label)
    for c in sources:
        label = _normalize_label(c.get("label", ""))
        if label == needle:
            return _normalize_combo(c)
    return None


def _normalize_combo(c: dict) -> dict:
    """Normalize field names from combination_search JSON to what validator expects."""
    out = dict(c)
    # combination_search uses n_total + win_rate_pct; validator expects n + wr_pct
    if "n_total" in out and "n" not in out:
        out["n"] = out["n_total"]
    if "win_rate_pct" in out and "wr_pct" not in out:
        out["wr_pct"] = out["win_rate_pct"]
    return out


def run_walk_forward(csv: str, vix_csv: str, train_end: str, test_start: str,
                     test_end: str, target_combos: list[str]) -> dict:
    """Run train + test windows and compare WR for each target combo."""
    print(f"[wf-validator] Train window: 2025-01-01 to {train_end}")
    print(f"[wf-validator] Test window:  {test_start} to {test_end}")

    # Use loose gates so we can find the combos even if they barely pass in sub-windows
    train = _run_search(csv, vix_csv, "2025-01-01", train_end, min_n=5, wr_floor=40.0)
    test  = _run_search(csv, vix_csv, test_start, test_end, min_n=5, wr_floor=40.0)

    results = []
    for combo in target_combos:
        train_hit = _find_combo_anywhere(train, combo)
        test_hit  = _find_combo_anywhere(test, combo)

        train_wr = train_hit["wr_pct"] if train_hit else None
        test_wr  = test_hit["wr_pct"]  if test_hit  else None
        train_n  = train_hit["n"]       if train_hit else 0
        test_n   = test_hit["n"]        if test_hit  else 0
        delta    = round(test_wr - train_wr, 1) if (train_wr and test_wr) else None

        verdict = "STABLE"
        if delta is None:
            verdict = "MISSING_IN_TEST" if train_hit else "NOT_FOUND"
        elif delta < -8:
            verdict = "DEGRADED"
        elif delta > 5:
            verdict = "IMPROVED"

        results.append({
            "combo": combo,
            "train_n": train_n, "train_wr_pct": train_wr,
            "test_n": test_n,   "test_wr_pct": test_wr,
            "delta_pp": delta,
            "verdict": verdict,
        })
        status_icon = {"STABLE": "PASS", "IMPROVED": "PASS", "DEGRADED": "FAIL",
                       "MISSING_IN_TEST": "WARN", "NOT_FOUND": "WARN"}.get(verdict, "?")
        print(f"  [{status_icon}] {combo[:55]:<55}  train={train_wr}%/N={train_n}  test={test_wr}%/N={test_n}  delta={delta}pp  {verdict}")

    return {
        "train_end": train_end, "test_start": test_start, "test_end": test_end,
        "results": results,
        "pass_count": sum(1 for r in results if r["verdict"] in ("STABLE", "IMPROVED")),
        "total": len(results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk-forward validator for combo_search results")
    parser.add_argument("--csv",        required=True)
    parser.add_argument("--vix-csv",    required=True)
    parser.add_argument("--train-end",  default="2025-09-30")
    parser.add_argument("--test-start", default="2025-10-01")
    parser.add_argument("--test-end",   default="2026-05-15")
    parser.add_argument("--top-combos", nargs="+", default=[
        "momentum_acceleration|regime=ALIGNED|vix=HIGH_VOL",
        "double_bottom|prox=NOT_NEAR_NAMED|time=MORNING|vix=LOW_VOL",
        "double_bottom|prox=NOT_NEAR_NAMED|conf=LOW|vix=LOW_VOL",
    ])
    args = parser.parse_args()

    result = run_walk_forward(
        csv=args.csv, vix_csv=args.vix_csv,
        train_end=args.train_end, test_start=args.test_start, test_end=args.test_end,
        target_combos=args.top_combos,
    )

    out_path = ROOT / "analysis" / f"walk-forward-combination-{datetime.now().strftime('%Y-%m-%d')}.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n[wf-validator] {result['pass_count']}/{result['total']} combos STABLE/IMPROVED")
    print(f"[wf-validator] Output: {out_path}")
    return 0 if result["pass_count"] >= result["total"] - 1 else 1  # allow 1 DEGRADED


if __name__ == "__main__":
    sys.exit(main())
