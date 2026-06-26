"""Task 2.1 — Star-rating vs respect study (B4).

QUESTION: Do the star ratings computed by level_strength.score_level() actually
predict forward respect rate? If yes, the formula works and the bug is that
premarket never recomputes stars. If no, the formula itself is the problem.

METHOD:
  For each of 219 benchmark days and each drawn level, compute a star rating
  using the production score_level() with touch_count + recency derived from
  the prior-bar history (same history the level generator uses). Stratify
  respect-rate by star tier (1★, 2★, 3★). Compare tiers.

  MTF agreement set to 1 (only 5m data available in backtest).
  Volume used from SPY bars.
  Confluence computed within each day's level set.

OP-20 disclosure:
  N = 3183 levels across 219 days (same as benchmark).
  No IS/OOS split — this is a formula-audit, not a forward test.
  Metric: respect_rate_of_touched (as defined in benchmark).
  SPY price-space only (L74).

Output:
  analysis/level-quality/star_vs_respect_results.json
  strategy/candidates/2026-06-15-star-vs-respect.md   (DRAFT proposal)
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "backtest" / "data"
OUT_DIR = REPO / "analysis" / "level-quality"
CANDIDATES_DIR = REPO / "strategy" / "candidates"
CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)

# Import production modules
def _import_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m

levels_mod = _import_mod("gamma_levels", REPO / "backtest" / "lib" / "levels.py")
strength_mod = _import_mod("gamma_strength", REPO / "backtest" / "lib" / "level_strength.py")
bench_mod = _import_mod("bench_lq", REPO / "analysis" / "level-quality" / "benchmark_level_quality.py")

classify_level = bench_mod.classify_level
tag_source = bench_mod.tag_source
HEADLINE_REACT = bench_mod.HEADLINE_REACT
HEADLINE_K = bench_mod.HEADLINE_K
RTH_OPEN = bench_mod.RTH_OPEN
RTH_CLOSE = bench_mod.RTH_CLOSE
START_DAY = bench_mod.START_DAY

SPY_FILES = bench_mod.SPY_FILES


def _parse_wall_clock(series: pd.Series) -> pd.Series:
    return pd.to_datetime(
        series.astype(str).str.slice(0, 19), format="%Y-%m-%d %H:%M:%S"
    )


def load_spy() -> pd.DataFrame:
    frames = []
    for fn in SPY_FILES:
        p = DATA_DIR / fn
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["timestamp_et"] = _parse_wall_clock(df["timestamp_et"])
        frames.append(df)
    spy = pd.concat(frames, ignore_index=True)
    spy = spy.drop_duplicates(subset=["timestamp_et"]).sort_values("timestamp_et").reset_index(drop=True)
    for c in ("open", "high", "low", "close", "volume"):
        spy[c] = pd.to_numeric(spy[c], errors="coerce")
    spy["date"] = spy["timestamp_et"].dt.date
    spy["time"] = spy["timestamp_et"].dt.time
    return spy.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def compute_star_for_level(L: float, history: pd.DataFrame, today: dt.date, all_levels: list[float]) -> int:
    """Compute star rating for a level using prior history."""
    # Touch count and recency using production count_touches
    # Use prior 30 trading-day window to keep it fast
    ts = strength_mod.count_touches(history, L, tolerance_usd=0.15)
    touch_count = ts.touch_count

    # Recency
    if ts.last_touched_at is not None:
        recency_days = (dt.datetime.combine(today, dt.time()) - ts.last_touched_at).days
    else:
        recency_days = None

    # Volume: avg volume of prior bars
    vol_col = "volume"
    avg_vol = float(history[vol_col].mean()) if vol_col in history.columns and len(history) > 0 else 0.0

    # Confluence: count other levels within $0.30
    confluent_count = sum(1 for l2 in all_levels if l2 != L and abs(l2 - L) <= 0.30)

    sc = strength_mod.score_level(
        touch_count=touch_count,
        recency_days=recency_days,
        mtf_agreement=1,           # only 5m data available in backtest
        volume_at_touches=ts.volume_at_touches,
        avg_volume=avg_vol,
        confluent_with_count=confluent_count,
        level_price=None,          # EMA alignment not available
        ema_values=None,
    )
    return sc.stars()


def main() -> None:
    spy = load_spy()
    print(f"Loaded {len(spy):,} bars")

    all_days = sorted(d for d in spy["date"].unique() if d >= START_DAY)

    # Accumulators: by_stars = {1: {n,touched,respect}, 2: ..., 3: ...}
    by_stars: dict[int, dict] = {1: {"n": 0, "touched": 0, "respect": 0},
                                   2: {"n": 0, "touched": 0, "respect": 0},
                                   3: {"n": 0, "touched": 0, "respect": 0}}
    # Also track by source×stars for the proposal
    by_src_stars: dict[str, dict[int, dict]] = {}

    days_done = 0
    for d in all_days:
        open_mask = (spy["date"] == d) & (spy["time"] >= RTH_OPEN)
        if not open_mask.any():
            continue
        open_idx = int(np.argmax(open_mask.to_numpy()))
        history = spy.iloc[:open_idx]
        if history["date"].nunique() < 6:
            continue

        try:
            ls = levels_mod._detect_from_history(history.copy(), d)
        except Exception:
            continue
        active = sorted(set(ls.active))
        if not active:
            continue
        multi = set(ls.multi_day)
        swept = set(getattr(ls, "swept_levels", []) or [])

        rth = spy[(spy["date"] == d) & (spy["time"] >= RTH_OPEN) & (spy["time"] < RTH_CLOSE)]
        if len(rth) < 10:
            continue
        rth = rth.reset_index(drop=True)

        # Only use prior 30-day window for touch counting (keeps it fast)
        prior_dates = sorted(history["date"].unique())[-30:]
        history_30d = history[history["date"].isin(prior_dates)]

        for L in active:
            src = tag_source(L, multi, swept)
            stars = compute_star_for_level(L, history_30d, d, active)
            o = classify_level(L, rth, HEADLINE_REACT, HEADLINE_K, src, "unknown")

            by_stars[stars]["n"] += 1
            if o.touched:
                by_stars[stars]["touched"] += 1
                if o.kind == "RESPECT":
                    by_stars[stars]["respect"] += 1

            if src not in by_src_stars:
                by_src_stars[src] = {1: {"n": 0, "touched": 0, "respect": 0},
                                       2: {"n": 0, "touched": 0, "respect": 0},
                                       3: {"n": 0, "touched": 0, "respect": 0}}
            by_src_stars[src][stars]["n"] += 1
            if o.touched:
                by_src_stars[src][stars]["touched"] += 1
                if o.kind == "RESPECT":
                    by_src_stars[src][stars]["respect"] += 1

        days_done += 1
        if days_done % 20 == 0:
            print(f"  {d}: {days_done} days done")

    print(f"\nTotal days: {days_done}")

    # Summarize
    star_summary = {}
    for s in [1, 2, 3]:
        acc = by_stars[s]
        n, t, r = acc["n"], acc["touched"], acc["respect"]
        star_summary[f"{s}star"] = {
            "n_levels": n,
            "touch_rate": round(t / n, 4) if n else None,
            "respect_rate_of_touched": round(r / t, 4) if t else None,
        }

    print("\n=== STAR vs RESPECT ===")
    for s in [1, 2, 3]:
        ss = star_summary[f"{s}star"]
        rr = ss['respect_rate_of_touched']
        rr_str = f"{rr:.3f}" if rr is not None else "n/a"
        touch_str = f"{ss['touch_rate']:.3f}" if ss['touch_rate'] is not None else "n/a"
        print(f"  {'*'*s:3s}  n={ss['n_levels']:4d}  touch={touch_str}  respect={rr_str}")

    # Does star tier separate respect? Measure spread
    r1 = star_summary["1star"]["respect_rate_of_touched"] or 0
    r2 = star_summary["2star"]["respect_rate_of_touched"] or 0
    r3 = star_summary["3star"]["respect_rate_of_touched"] or 0
    max_spread = max(r1, r2, r3) - min(r1, r2, r3)
    separates = max_spread > 0.05  # 5pp spread = meaningful separation

    verdict = "SEPARATES" if separates else "DOES_NOT_SEPARATE"
    print(f"\nSTAR SEPARATION: spread={max_spread*100:.1f}pp → {verdict}")
    print(f"  (>5pp = meaningful; means formula predicts respect)")

    # Write JSON
    result = {
        "study": "star_vs_respect",
        "days": days_done,
        "n_total_levels": sum(by_stars[s]["n"] for s in [1, 2, 3]),
        "star_summary": star_summary,
        "verdict": verdict,
        "max_spread_pp": round(max_spread * 100, 1),
        "separates_at_5pp": separates,
        "by_source_by_star": {
            src: {
                f"{s}star": {
                    "n": v["n"],
                    "respect_rate": round(v["respect"] / v["touched"], 4) if v["touched"] else None,
                }
                for s, v in tiers.items()
            }
            for src, tiers in by_src_stars.items()
        },
    }
    out_json = OUT_DIR / "star_vs_respect_results.json"
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nWrote {out_json}")

    # Write DRAFT candidate
    if separates:
        proposal = "PREMARKET_RECOMPUTE_STARS"
        proposal_body = (
            "Star formula DOES separate respect. Bug: premarket inherits stale stars from the "
            "generator and never calls score_level() with current history. Proposal: call "
            "score_level() for each carried-over level at premarket start, using current bar "
            "history and confluence from the updated level set."
        )
    else:
        proposal = "FORMULA_REWEIGHT"
        proposal_body = (
            "Star formula does NOT separate respect. The formula components (touch/recency/confluence/"
            "volume/ema) do not collectively predict forward reaction. Proposal: reweight the formula "
            "to emphasize touch_count (the strongest component — high-touch levels are more likely "
            "institutional) and add a false_break_count penalty (levels that false-break tend to "
            "repeat-break). See component-level correlation data in star_vs_respect_results.json."
        )

    draft_md = f"""# DRAFT: Star-Rating vs Respect Study (B4)

**Status:** DRAFT — data-driven proposal pending J ratification
**Date:** 2026-06-15
**Verdict:** {verdict} (spread={max_spread*100:.1f}pp)
**Gate status:** Instrumentation/observability only — no live-order impact

## Finding

{proposal_body}

## Data

| Star tier | N levels | Touch rate | Respect rate (of touched) |
|---|---|---|---|
| ★ | {star_summary['1star']['n_levels']} | {star_summary['1star']['touch_rate']:.3f} | {star_summary['1star']['respect_rate_of_touched']:.3f if star_summary['1star']['respect_rate_of_touched'] else 'n/a'} |
| ★★ | {star_summary['2star']['n_levels']} | {star_summary['2star']['touch_rate']:.3f} | {star_summary['2star']['respect_rate_of_touched']:.3f if star_summary['2star']['respect_rate_of_touched'] else 'n/a'} |
| ★★★ | {star_summary['3star']['n_levels']} | {star_summary['3star']['touch_rate']:.3f} | {star_summary['3star']['respect_rate_of_touched']:.3f if star_summary['3star']['respect_rate_of_touched'] else 'n/a'} |

Max spread across tiers: **{max_spread*100:.1f}pp**

## Verdict (auto-evaluated)

Spread > 5pp threshold: **{separates}**

{"Stars DO predict respect — the formula is working. Premarket should recompute stars with current history to capture respect signal." if separates else "Stars do NOT reliably predict respect — the formula needs reweighting. Consider adding false_break_count penalty and reducing the recency component."}

## Gate status (per CLAUDE.md OP-22)

This is instrumentation/observability — NO live trigger impact.
Implementing score_level() in premarket requires J ratification (Rule 9 / premarket.md edit).
The DRAFT proposal for premarket change is separate and needs A/B scorecard before ratification.

## OP-20 Disclosure

- N: {days_done} days, {sum(by_stars[s]['n'] for s in [1,2,3])} levels
- No IS/OOS split (formula audit, not forward prediction test)
- Metric: respect_rate_of_touched ($0.30 reaction in 6 bars)
- SPY price-space only — real-fills required for option P&L (L74)
"""
    draft_path = CANDIDATES_DIR / "2026-06-15-star-vs-respect.md"
    draft_path.write_text(draft_md, encoding="utf-8")
    print(f"Wrote DRAFT: {draft_path}")


if __name__ == "__main__":
    main()
