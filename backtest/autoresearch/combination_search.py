"""combination_search -- systematic combo search across detector x filter dimensions.

Tunes the existing pattern detectors against a historical window without building
any new primitives. Uses pattern_backtest.run_pattern_backtest to harvest per-hit
records on each day, then re-filters at aggregate-time across a 6-dimensional
combo space and ranks survivors by `edge_capture * sharpe` (per OP-16).

DIMENSIONS (8 detectors x 4 regime x 3 proximity x 4 confidence x 3 time x 3 vix
        = ~2,592 combos when all detectors fire in the window):

    detector_name      -- one of the gradeable detectors found in the dataset
    regime_filter      -- ANY | ALIGNED | CONTRARY | FLAT
    proximity_filter   -- ANY | NEAR_NAMED | NOT_NEAR_NAMED
    confidence_band    -- ANY | LOW (<0.65) | MID (0.65-0.80) | HIGH (>=0.80)
    time_band          -- ANY | MORNING (09:30-11:30) | AFTERNOON (11:30-15:55)
    vix_band           -- ANY | LOW_VOL (vix<20) | HIGH_VOL (vix>=20)

GATES (per OP-20 disclosure standard):

    sample_size:        N >= min_n        (default 20)
    win_rate:           WR >= wr_floor    (default 50.0)
    month_stability:    >= min_months_active months with >=1 hit
    concentration:      max_month_share <= max_month_concentration (default 0.50)

OUTPUT:

    analysis/combination-search-{START}-to-{END}.json   -- full ranked results
    analysis/combination-search-{START}-to-{END}.md     -- top-N leaderboard

CLI:

    python combination_search.py --range 2025-12-01 2026-03-31
    python combination_search.py --range 2025-12-01 2026-03-31 --top-n 25 --min-n 30
    python combination_search.py --range 2025-12-01 2026-03-31 --no-vix

Per CLAUDE.md OP-22 (Don't Stop Cooking) + OP-25 (ENGINE-BENEFIT AUTONOMY):
    This is observer-only research. Writes ranked candidates to `analysis/`.
    Does NOT modify any production doctrine, params*.json, heartbeat.md, or
    place any orders. Any winner that promotes follows OP-21 watch-only path.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from dataclasses import dataclass, field
from datetime import date as Date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

# Make crypto + autoresearch importable
PROJECT_ROOT = Path(__file__).resolve().parents[2]
for p in (PROJECT_ROOT, PROJECT_ROOT / "backtest"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Sibling-file imports (match pattern_backtest.py style)
from autoresearch.pattern_backtest import (  # noqa: E402
    _load_bars_for_date,
    run_pattern_backtest,
)
from crypto.lib.bar import Bar  # noqa: E402


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

ET = timezone(timedelta(hours=-4))

CONFIDENCE_THRESHOLDS: dict[str, tuple[float, float]] = {
    "ANY": (0.0, 1.01),
    "LOW": (0.0, 0.65),
    "MID": (0.65, 0.80),
    "HIGH": (0.80, 1.01),
}

TIME_BANDS: dict[str, tuple[time, time]] = {
    "ANY": (time(9, 30), time(16, 0)),
    "MORNING": (time(9, 30), time(11, 30)),
    "AFTERNOON": (time(11, 30), time(15, 55)),
}

VIX_BANDS: dict[str, tuple[float, float]] = {
    "ANY": (0.0, 1000.0),
    "LOW_VOL": (0.0, 20.0),
    "HIGH_VOL": (20.0, 1000.0),
}

REGIME_FILTERS: tuple[str, ...] = ("ANY", "ALIGNED", "CONTRARY", "FLAT")
PROXIMITY_FILTERS: tuple[str, ...] = ("ANY", "NEAR_NAMED", "NOT_NEAR_NAMED")

# Inside-bar is by-design neutral (no WIN/LOSS grade) — exclude from ranking.
EXCLUDED_DETECTOR_PREFIXES: tuple[str, ...] = ("inside_bar",)


# ---------------------------------------------------------------------------
# DATA SHAPES
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HitRecord:
    """One graded pattern hit, enriched with all combo-search dimensions."""
    trade_date: Date
    detector: str
    bias: str  # "bullish" | "bearish" | "neutral"
    confidence: float
    bar_time_et: time
    bar_close: float
    next_bar_move: float  # signed: positive = winning direction for this bias
    grade: str  # "WIN" | "LOSS" | "NEUTRAL"
    regime: str  # "uptrend" | "downtrend" | "flat" | "unknown"
    regime_aligned: bool
    near_key_level: bool
    vix_at_bar: float | None  # None when no VIX CSV or no match


@dataclass(frozen=True, slots=True)
class ComboKey:
    """The 6-tuple defining a combo."""
    detector: str
    regime_filter: str
    proximity_filter: str
    confidence_band: str
    time_band: str
    vix_band: str

    def as_label(self) -> str:
        parts = [self.detector]
        if self.regime_filter != "ANY":
            parts.append(f"regime={self.regime_filter}")
        if self.proximity_filter != "ANY":
            parts.append(f"prox={self.proximity_filter}")
        if self.confidence_band != "ANY":
            parts.append(f"conf={self.confidence_band}")
        if self.time_band != "ANY":
            parts.append(f"time={self.time_band}")
        if self.vix_band != "ANY":
            parts.append(f"vix={self.vix_band}")
        return " | ".join(parts)


@dataclass(frozen=True, slots=True)
class ComboMetrics:
    """Computed metrics for one combo over the corpus."""
    combo: ComboKey
    n_total: int
    n_wins: int
    n_losses: int
    n_neutral: int
    win_rate_pct: float
    edge_capture_dollars: float  # sum of signed next-bar moves
    avg_move_dollars: float
    std_move_dollars: float
    sharpe_proxy: float  # avg / std (0 if std == 0)
    final_score: float  # edge_capture * sharpe_proxy
    months_active: int
    max_month_share: float
    gates_passed: bool
    gate_failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchConfig:
    """All knobs for one search invocation."""
    range_start: Date
    range_end: Date
    csv_path: Path
    vix_csv_path: Path | None
    min_n: int
    wr_floor: float
    min_months_active: int
    max_month_concentration: float
    top_n: int
    output_dir: Path


# ---------------------------------------------------------------------------
# VIX LOADER
# ---------------------------------------------------------------------------


def _load_vix_close_by_minute(vix_csv: Path) -> dict[tuple[Date, time], float]:
    """Build a lookup: (date, HH:MM) -> vix close.

    The vix_5m CSV has timestamp_et column in naive ISO format (no tz suffix).
    """
    lookup: dict[tuple[Date, time], float] = {}
    if not vix_csv.exists():
        return lookup
    with vix_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_str = row.get("timestamp_et", "")
            try:
                # Tolerate both naive and tz-suffixed formats.
                if "+" in ts_str or ts_str.count("-") > 2:
                    ts = datetime.fromisoformat(ts_str)
                else:
                    ts = datetime.fromisoformat(ts_str)
            except ValueError:
                continue
            try:
                vix_close = float(row.get("close", ""))
            except (TypeError, ValueError):
                continue
            # Round timestamp to its 5-minute boundary (matches SPY bars).
            t = time(ts.hour, ts.minute - (ts.minute % 5))
            lookup[(ts.date(), t)] = vix_close
    return lookup


def _lookup_vix(
    vix_table: dict[tuple[Date, time], float],
    trade_date: Date,
    bar_time_et: time,
) -> float | None:
    """Find the VIX close at the given (date, time). Falls back to the prior
    5-minute slot up to 3 steps if exact match missing (gaps on the VIX feed
    are common; we accept up to 15 min staleness)."""
    if not vix_table:
        return None
    candidate = time(bar_time_et.hour, bar_time_et.minute - (bar_time_et.minute % 5))
    for _ in range(4):
        v = vix_table.get((trade_date, candidate))
        if v is not None:
            return v
        # Step back 5 minutes
        total_min = candidate.hour * 60 + candidate.minute - 5
        if total_min < 0:
            return None
        candidate = time(total_min // 60, total_min % 60)
    return None


# ---------------------------------------------------------------------------
# HIT HARVESTING
# ---------------------------------------------------------------------------


def _iter_trading_dates(start: Date, end: Date) -> Iterable[Date]:
    """Yield calendar dates Mon-Fri inclusive. (No holiday filter; pattern_backtest
    will return error for non-trading days and we skip them.)"""
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def _parse_bar_time_et(bar_time_str: str) -> time:
    """Parse 'HH:MM' into a time object."""
    hh, mm = bar_time_str.split(":")[:2]
    return time(int(hh), int(mm))


def _harvest_day_hits(
    trade_date: Date,
    csv_path: Path,
    vix_table: dict[tuple[Date, time], float],
) -> list[HitRecord]:
    """Run pattern_backtest for one day, re-load bars for next-bar moves,
    and emit one HitRecord per gradeable pattern hit."""
    result = run_pattern_backtest(trade_date, csv_path, prior_day_context=1)
    if "error" in result or "hits" not in result:
        return []

    bars, _ = _load_bars_for_date(csv_path, trade_date, prior_day_context=1)
    if not bars:
        return []

    out: list[HitRecord] = []
    for hit_dict in result["hits"]:
        det = hit_dict.get("detector", "")
        if any(det.startswith(prefix) for prefix in EXCLUDED_DETECTOR_PREFIXES):
            continue

        bias = hit_dict.get("bias", "neutral")
        grade = hit_dict.get("grade_next_bar", "NEUTRAL")
        if bias == "neutral":
            continue  # un-gradeable

        bar_idx = int(hit_dict.get("bar_index", -1))
        if bar_idx < 0 or bar_idx + 1 >= len(bars):
            continue

        cur_close = float(bars[bar_idx].close)
        next_close = float(bars[bar_idx + 1].close)
        # Signed move in the bias direction (positive = winning move)
        raw_move = next_close - cur_close
        if bias == "bullish":
            next_bar_move = raw_move
        else:  # bearish
            next_bar_move = -raw_move

        bar_time_et = _parse_bar_time_et(hit_dict.get("bar_time_et", "00:00"))
        notes = hit_dict.get("notes") or {}
        near_key = bool(notes.get("near_key_level", False))

        regime = hit_dict.get("regime", "unknown")
        regime_aligned = bool(hit_dict.get("regime_aligned", False))

        vix_val = _lookup_vix(vix_table, trade_date, bar_time_et)

        out.append(HitRecord(
            trade_date=trade_date,
            detector=det,
            bias=bias,
            confidence=float(hit_dict.get("confidence", 0.0)),
            bar_time_et=bar_time_et,
            bar_close=cur_close,
            next_bar_move=next_bar_move,
            grade=grade,
            regime=regime,
            regime_aligned=regime_aligned,
            near_key_level=near_key,
            vix_at_bar=vix_val,
        ))
    return out


# ---------------------------------------------------------------------------
# COMBO FILTER PREDICATES
# ---------------------------------------------------------------------------


def _match_regime(hit: HitRecord, regime_filter: str) -> bool:
    if regime_filter == "ANY":
        return True
    if regime_filter == "ALIGNED":
        return hit.regime_aligned
    if regime_filter == "CONTRARY":
        # Contrary = trending regime that is opposite to the bias
        if hit.regime not in ("uptrend", "downtrend"):
            return False
        return not hit.regime_aligned
    if regime_filter == "FLAT":
        return hit.regime not in ("uptrend", "downtrend")
    return False


def _match_proximity(hit: HitRecord, proximity_filter: str) -> bool:
    if proximity_filter == "ANY":
        return True
    if proximity_filter == "NEAR_NAMED":
        return hit.near_key_level
    if proximity_filter == "NOT_NEAR_NAMED":
        return not hit.near_key_level
    return False


def _match_confidence(hit: HitRecord, band: str) -> bool:
    lo, hi = CONFIDENCE_THRESHOLDS[band]
    return lo <= hit.confidence < hi


def _match_time(hit: HitRecord, band: str) -> bool:
    lo, hi = TIME_BANDS[band]
    return lo <= hit.bar_time_et < hi


def _match_vix(hit: HitRecord, band: str) -> bool:
    if band == "ANY":
        return True
    if hit.vix_at_bar is None:
        return False  # Cannot satisfy a non-ANY VIX band without data
    lo, hi = VIX_BANDS[band]
    return lo <= hit.vix_at_bar < hi


def _hit_matches_combo(hit: HitRecord, combo: ComboKey) -> bool:
    if hit.detector != combo.detector:
        return False
    return (
        _match_regime(hit, combo.regime_filter)
        and _match_proximity(hit, combo.proximity_filter)
        and _match_confidence(hit, combo.confidence_band)
        and _match_time(hit, combo.time_band)
        and _match_vix(hit, combo.vix_band)
    )


# ---------------------------------------------------------------------------
# COMBO METRICS
# ---------------------------------------------------------------------------


def _compute_metrics(
    combo: ComboKey,
    matching_hits: list[HitRecord],
    cfg: SearchConfig,
) -> ComboMetrics:
    n_total = len(matching_hits)
    n_wins = sum(1 for h in matching_hits if h.grade == "WIN")
    n_losses = sum(1 for h in matching_hits if h.grade == "LOSS")
    n_neutral = n_total - n_wins - n_losses

    moves = [h.next_bar_move for h in matching_hits if h.grade in ("WIN", "LOSS")]
    n_graded = len(moves)
    win_rate_pct = (n_wins / n_graded * 100.0) if n_graded > 0 else 0.0
    edge_capture = sum(moves)
    avg_move = edge_capture / n_graded if n_graded > 0 else 0.0
    if n_graded > 1:
        std_move = statistics.pstdev(moves)
    else:
        std_move = 0.0
    sharpe_proxy = (avg_move / std_move) if std_move > 0 else 0.0
    # Sign-safe scoring: when edge_capture is positive, weight by sharpe (reward
    # consistency). When edge_capture is negative (loser combo), DO NOT let a
    # negative sharpe (negative avg_move / positive std) flip the product positive
    # and rank a loser ABOVE a real winner. Use edge_capture itself as the floor.
    if edge_capture > 0 and sharpe_proxy > 0:
        final_score = edge_capture * sharpe_proxy
    else:
        final_score = edge_capture

    # Month stability + concentration
    by_month: dict[str, int] = {}
    for h in matching_hits:
        ym = f"{h.trade_date.year:04d}-{h.trade_date.month:02d}"
        by_month[ym] = by_month.get(ym, 0) + 1
    months_active = len(by_month)
    max_month_share = (max(by_month.values()) / n_total) if n_total > 0 else 0.0

    # Gates
    failures: list[str] = []
    if n_graded < cfg.min_n:
        failures.append(f"n<{cfg.min_n}")
    if win_rate_pct < cfg.wr_floor:
        failures.append(f"wr<{cfg.wr_floor:.0f}%")
    if months_active < cfg.min_months_active:
        failures.append(f"months<{cfg.min_months_active}")
    if max_month_share > cfg.max_month_concentration:
        failures.append(f"month_share>{cfg.max_month_concentration:.2f}")

    return ComboMetrics(
        combo=combo,
        n_total=n_total,
        n_wins=n_wins,
        n_losses=n_losses,
        n_neutral=n_neutral,
        win_rate_pct=round(win_rate_pct, 2),
        edge_capture_dollars=round(edge_capture, 4),
        avg_move_dollars=round(avg_move, 4),
        std_move_dollars=round(std_move, 4),
        sharpe_proxy=round(sharpe_proxy, 4),
        final_score=round(final_score, 4),
        months_active=months_active,
        max_month_share=round(max_month_share, 3),
        gates_passed=len(failures) == 0,
        gate_failures=tuple(failures),
    )


# ---------------------------------------------------------------------------
# COMBO SPACE GENERATOR
# ---------------------------------------------------------------------------


def _enumerate_combos(detectors_seen: list[str], use_vix: bool) -> list[ComboKey]:
    vix_bands = list(VIX_BANDS.keys()) if use_vix else ["ANY"]
    out: list[ComboKey] = []
    for det in detectors_seen:
        for rf in REGIME_FILTERS:
            for pf in PROXIMITY_FILTERS:
                for cb in CONFIDENCE_THRESHOLDS.keys():
                    for tb in TIME_BANDS.keys():
                        for vb in vix_bands:
                            out.append(ComboKey(
                                detector=det,
                                regime_filter=rf,
                                proximity_filter=pf,
                                confidence_band=cb,
                                time_band=tb,
                                vix_band=vb,
                            ))
    return out


# ---------------------------------------------------------------------------
# MAIN RUNNER
# ---------------------------------------------------------------------------


def run_search(cfg: SearchConfig) -> dict[str, Any]:
    """Harvest hits across the date range, enumerate combos, compute metrics,
    rank survivors. Returns the full output dict (also written to disk)."""

    # 1. Build VIX lookup (optional)
    vix_table: dict[tuple[Date, time], float] = {}
    if cfg.vix_csv_path is not None:
        print(f"  Loading VIX from {cfg.vix_csv_path.name}...")
        vix_table = _load_vix_close_by_minute(cfg.vix_csv_path)
        print(f"  VIX rows loaded: {len(vix_table):,}")

    # 2. Harvest hits day-by-day
    all_hits: list[HitRecord] = []
    days_with_data = 0
    days_skipped = 0
    for trade_date in _iter_trading_dates(cfg.range_start, cfg.range_end):
        try:
            day_hits = _harvest_day_hits(trade_date, cfg.csv_path, vix_table)
        except Exception as exc:  # noqa: BLE001 — observability
            print(f"  {trade_date}: harvest_error: {exc}", file=sys.stderr)
            days_skipped += 1
            continue
        if not day_hits:
            days_skipped += 1
            continue
        all_hits.extend(day_hits)
        days_with_data += 1

    print(f"  Harvest complete: {days_with_data} days with hits, "
          f"{days_skipped} skipped, {len(all_hits):,} total hits")

    # 3. Detector population (which ones actually fired in this corpus)
    detectors_seen = sorted({h.detector for h in all_hits})
    print(f"  Detectors seen in corpus: {len(detectors_seen)}")
    for d in detectors_seen:
        n_d = sum(1 for h in all_hits if h.detector == d)
        print(f"    {d:<46s} {n_d:>5d} hits")

    # 4. Enumerate combos
    use_vix = bool(vix_table)
    combos = _enumerate_combos(detectors_seen, use_vix=use_vix)
    print(f"  Combo space size: {len(combos):,} (use_vix={use_vix})")

    # 5. Compute metrics per combo
    #    Pre-index hits by detector to avoid scanning all-hits each combo.
    hits_by_detector: dict[str, list[HitRecord]] = {}
    for h in all_hits:
        hits_by_detector.setdefault(h.detector, []).append(h)

    all_metrics: list[ComboMetrics] = []
    for combo in combos:
        detector_hits = hits_by_detector.get(combo.detector, [])
        matching = [h for h in detector_hits if _hit_matches_combo(h, combo)]
        all_metrics.append(_compute_metrics(combo, matching, cfg))

    # 6. Rank: gates-passed combos first by final_score (desc), then non-passing
    passing = [m for m in all_metrics if m.gates_passed]
    failing = [m for m in all_metrics if not m.gates_passed]
    passing.sort(key=lambda m: (m.final_score, m.edge_capture_dollars), reverse=True)
    failing.sort(key=lambda m: (m.final_score, m.edge_capture_dollars), reverse=True)

    print(f"  Combos passing all gates: {len(passing)} / {len(all_metrics)}")

    # 7. Build output
    output = {
        "range_start": cfg.range_start.isoformat(),
        "range_end": cfg.range_end.isoformat(),
        "csv_path": str(cfg.csv_path),
        "vix_csv_path": str(cfg.vix_csv_path) if cfg.vix_csv_path else None,
        "days_with_data": days_with_data,
        "days_skipped": days_skipped,
        "total_hits": len(all_hits),
        "detectors_seen": detectors_seen,
        "combo_space_size": len(combos),
        "gates": {
            "min_n": cfg.min_n,
            "wr_floor": cfg.wr_floor,
            "min_months_active": cfg.min_months_active,
            "max_month_concentration": cfg.max_month_concentration,
        },
        "passing_combos_count": len(passing),
        "top_passing": [_metrics_to_dict(m) for m in passing[: cfg.top_n]],
        "top_failing_by_score": [
            _metrics_to_dict(m) for m in failing[:5]
        ],
        # Per-detector best combo (for at-a-glance per-detector tuning view)
        "best_per_detector": _best_per_detector(passing, detectors_seen),
    }

    return output


def _metrics_to_dict(m: ComboMetrics) -> dict[str, Any]:
    return {
        "label": m.combo.as_label(),
        "detector": m.combo.detector,
        "regime_filter": m.combo.regime_filter,
        "proximity_filter": m.combo.proximity_filter,
        "confidence_band": m.combo.confidence_band,
        "time_band": m.combo.time_band,
        "vix_band": m.combo.vix_band,
        "n_total": m.n_total,
        "n_wins": m.n_wins,
        "n_losses": m.n_losses,
        "n_neutral": m.n_neutral,
        "win_rate_pct": m.win_rate_pct,
        "edge_capture_dollars": m.edge_capture_dollars,
        "avg_move_dollars": m.avg_move_dollars,
        "std_move_dollars": m.std_move_dollars,
        "sharpe_proxy": m.sharpe_proxy,
        "final_score": m.final_score,
        "months_active": m.months_active,
        "max_month_share": m.max_month_share,
        "gates_passed": m.gates_passed,
        "gate_failures": list(m.gate_failures),
    }


def _best_per_detector(
    passing: list[ComboMetrics],
    detectors_seen: list[str],
) -> dict[str, dict[str, Any] | None]:
    out: dict[str, dict[str, Any] | None] = {}
    for det in detectors_seen:
        det_passing = [m for m in passing if m.combo.detector == det]
        if not det_passing:
            out[det] = None
            continue
        best = max(det_passing, key=lambda m: m.final_score)
        out[det] = _metrics_to_dict(best)
    return out


# ---------------------------------------------------------------------------
# MARKDOWN REPORT
# ---------------------------------------------------------------------------


def _format_md_report(output: dict[str, Any], cfg: SearchConfig) -> str:
    lines: list[str] = []
    lines.append(f"# Combination Search Leaderboard "
                 f"-- {output['range_start']} to {output['range_end']}")
    lines.append("")
    lines.append(f"**Days with data:** {output['days_with_data']}  ")
    lines.append(f"**Total graded hits:** {output['total_hits']:,}  ")
    lines.append(f"**Detectors in corpus:** {len(output['detectors_seen'])}  ")
    lines.append(f"**Combo space size:** {output['combo_space_size']:,}  ")
    lines.append(f"**Combos passing all gates:** {output['passing_combos_count']:,}  ")
    lines.append("")
    lines.append("**Gates:**  ")
    g = output["gates"]
    lines.append(f"- `min_n` >= {g['min_n']}")
    lines.append(f"- `win_rate` >= {g['wr_floor']:.1f}%")
    lines.append(f"- `min_months_active` >= {g['min_months_active']}")
    lines.append(f"- `max_month_concentration` <= {g['max_month_concentration']:.2f}")
    lines.append("")
    lines.append("> **Ranking metric:** `final_score = edge_capture_dollars * sharpe_proxy` "
                 "(per OP-16). Edge-capture is the sum of signed next-bar moves; sharpe-proxy "
                 "is avg/std of those moves.")
    lines.append("")

    lines.append(f"## Top {cfg.top_n} Combos (all gates PASS)")
    lines.append("")
    lines.append("| # | Combo | N | WR | EdgeCap $ | AvgMv $ | Sharpe | Score |")
    lines.append("|---|-------|---|----|-----------|---------|--------|-------|")
    for i, row in enumerate(output["top_passing"], start=1):
        lines.append(
            f"| {i} | {row['label']} "
            f"| {row['n_total']} "
            f"| {row['win_rate_pct']:.1f}% "
            f"| {row['edge_capture_dollars']:+.3f} "
            f"| {row['avg_move_dollars']:+.4f} "
            f"| {row['sharpe_proxy']:.3f} "
            f"| {row['final_score']:+.4f} |"
        )
    if not output["top_passing"]:
        lines.append("| — | _no combo passed all gates_ | | | | | | |")
    lines.append("")

    lines.append("## Best Combo Per Detector (gates-passing only)")
    lines.append("")
    lines.append("| Detector | Best combo | N | WR | EdgeCap $ | Score |")
    lines.append("|----------|------------|---|----|-----------|-------|")
    for det, row in output["best_per_detector"].items():
        if row is None:
            lines.append(f"| `{det}` | _no passing combo_ | — | — | — | — |")
        else:
            lines.append(
                f"| `{det}` | {row['label']} "
                f"| {row['n_total']} "
                f"| {row['win_rate_pct']:.1f}% "
                f"| {row['edge_capture_dollars']:+.3f} "
                f"| {row['final_score']:+.4f} |"
            )
    lines.append("")

    lines.append("## Top Failing Combos (for diagnostic context)")
    lines.append("")
    lines.append("| Combo | N | WR | EdgeCap $ | Score | Gate failures |")
    lines.append("|-------|---|----|-----------|-------|---------------|")
    for row in output["top_failing_by_score"]:
        gf = ", ".join(row["gate_failures"]) if row["gate_failures"] else "—"
        lines.append(
            f"| {row['label']} "
            f"| {row['n_total']} "
            f"| {row['win_rate_pct']:.1f}% "
            f"| {row['edge_capture_dollars']:+.3f} "
            f"| {row['final_score']:+.4f} "
            f"| {gf} |"
        )
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Per CLAUDE.md OP-22 + OP-25: observer-only research. "
                 "No production doctrine modified. Winning combos qualify for "
                 "OP-21 watch-only promotion path, not direct heartbeat wiring.*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _default_csv() -> Path:
    return PROJECT_ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-19_merged.csv"


def _default_vix_csv() -> Path:
    return PROJECT_ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-05-19_merged.csv"


def _default_output_dir() -> Path:
    return PROJECT_ROOT / "analysis"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Systematic combo search over the existing pattern detectors."
    )
    parser.add_argument(
        "--range",
        nargs=2,
        metavar=("START", "END"),
        required=True,
        help="Date range (inclusive), e.g. --range 2025-12-01 2026-03-31",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=_default_csv(),
        help="Path to SPY 5m merged CSV.",
    )
    parser.add_argument(
        "--vix-csv",
        type=Path,
        default=_default_vix_csv(),
        help="Path to VIX 5m merged CSV (used for vix_band dimension).",
    )
    parser.add_argument(
        "--no-vix",
        action="store_true",
        help="Disable VIX dimension. Reduces combo count ~3x.",
    )
    parser.add_argument(
        "--min-n",
        type=int,
        default=20,
        help="Minimum sample size for a combo to pass gates.",
    )
    parser.add_argument(
        "--wr-floor",
        type=float,
        default=50.0,
        help="Minimum win rate (percent) for a combo to pass gates.",
    )
    parser.add_argument(
        "--min-months-active",
        type=int,
        default=2,
        help="Minimum number of distinct months in which a combo had >=1 hit.",
    )
    parser.add_argument(
        "--max-month-concentration",
        type=float,
        default=0.60,
        help="Max share of a combo's hits allowed in a single month (0.0-1.0).",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Top-N combos to surface in MD leaderboard.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_default_output_dir(),
        help="Where to write the JSON + MD outputs.",
    )

    args = parser.parse_args()

    try:
        range_start = Date.fromisoformat(args.range[0])
        range_end = Date.fromisoformat(args.range[1])
    except ValueError as exc:
        print(f"ERROR: invalid --range dates: {exc}", file=sys.stderr)
        return 2
    if range_end < range_start:
        print(f"ERROR: --range END ({range_end}) precedes START ({range_start})",
              file=sys.stderr)
        return 2
    if not args.csv.exists():
        print(f"ERROR: SPY CSV not found at {args.csv}", file=sys.stderr)
        return 2

    vix_csv: Path | None = None
    if not args.no_vix:
        if args.vix_csv.exists():
            vix_csv = args.vix_csv
        else:
            print(f"  NOTE: --vix-csv not found at {args.vix_csv}; "
                  f"continuing without VIX dimension.", file=sys.stderr)

    cfg = SearchConfig(
        range_start=range_start,
        range_end=range_end,
        csv_path=args.csv,
        vix_csv_path=vix_csv,
        min_n=args.min_n,
        wr_floor=args.wr_floor,
        min_months_active=args.min_months_active,
        max_month_concentration=args.max_month_concentration,
        top_n=args.top_n,
        output_dir=args.output_dir,
    )

    print(f"=== Combination Search -- {range_start} to {range_end} ===")
    print(f"  CSV:     {cfg.csv_path.name}")
    print(f"  VIX CSV: {cfg.vix_csv_path.name if cfg.vix_csv_path else '(disabled)'}")
    print(f"  Gates:   min_n>={cfg.min_n}, wr>={cfg.wr_floor:.0f}%, "
          f"months>={cfg.min_months_active}, "
          f"month_concentration<={cfg.max_month_concentration:.2f}")
    print()

    output = run_search(cfg)

    # Persist outputs
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    out_stem = f"combination-search-{range_start}-to-{range_end}"
    out_json = cfg.output_dir / f"{out_stem}.json"
    out_md = cfg.output_dir / f"{out_stem}.md"
    out_json.write_text(json.dumps(output, indent=2), encoding="utf-8")
    out_md.write_text(_format_md_report(output, cfg), encoding="utf-8")

    print()
    print(f"  Wrote: {out_json.relative_to(PROJECT_ROOT)}")
    print(f"  Wrote: {out_md.relative_to(PROJECT_ROOT)}")
    print()
    if output["top_passing"]:
        top = output["top_passing"][0]
        print(f"  TOP COMBO: {top['label']}")
        print(f"    N={top['n_total']}  WR={top['win_rate_pct']:.1f}%  "
              f"EdgeCap=${top['edge_capture_dollars']:+.3f}  "
              f"Score={top['final_score']:+.4f}")
    else:
        print("  No combo passed all gates -- consider relaxing --min-n or --wr-floor.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
