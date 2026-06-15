"""V14E BEAR_HIGH_CONF sub-tier fingerprint analysis.

Drills into the N=33 bear + confidence=high observations to enumerate:
  1. Trigger combination fingerprints
  2. Time-of-day distribution (30-min buckets)
  3. VIX regime (from VIX daily close proxy, using vix_5m data)
  4. Score distribution (6-10)
  5. Outcome distribution (tp1_then_be_stop / runner_hit / stopped / other)
  6. Date coverage (session-level pattern — concentration check)
  7. Quality rank distribution
  8. Metadata: or_range, bar_type, SPY price proxies where available

Goal: identify what structural features make this 33-obs sub-tier special.
Decision: if fingerprints are stable + regime-independent → V14E promotion path can
  include a BEAR_HIGH_CONF fast-track (watch-only, N=50 target, WR≥80% minimum).

Output:
  analysis/backtests/v14e-bear-gate/highconf_fingerprint.json
  analysis/backtests/v14e-bear-gate/highconf_fingerprint.md

Per OP-22 (don't stop cooking) + OP-25 (engine-benefit autonomy).
"""
from __future__ import annotations

import json
import sys
import datetime as dt
from collections import Counter, defaultdict
from pathlib import Path

import os as _os

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

# pythonw stdout redirect (OP-27 L41)
if _os.path.basename(sys.executable).lower() == "pythonw.exe":
    _log_dir = ROOT / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    sys.stdout = open(_log_dir / "v14e_fingerprint.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_log_dir / "v14e_fingerprint.stderr.log", "a", buffering=1, encoding="utf-8")

OBS_FILE = ROOT / "automation" / "state" / "watcher-observations.jsonl"
VIX_DIR = ROOT / "backtest" / "data"
OUT_DIR = ROOT / "analysis" / "backtests" / "v14e-bear-gate"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = OUT_DIR / "highconf_fingerprint.json"
OUT_MD = OUT_DIR / "highconf_fingerprint.md"


def _parse_bar_ts(ts_str: str) -> dt.datetime | None:
    if not ts_str:
        return None
    try:
        # handle various tz suffix forms
        clean = ts_str.replace("T", " ")
        for suffix in ["+00:00", "+0000", "-04:00", "-0400", "-05:00", "-0500", "Z"]:
            if clean.endswith(suffix):
                clean = clean[: -len(suffix)]
                break
        # strip any remaining timezone offset (+HH:MM or -HH:MM form)
        import re
        clean = re.sub(r"[+-]\d{2}:\d{2}$", "", clean)
        clean = re.sub(r"[+-]\d{4}$", "", clean)
        return dt.datetime.fromisoformat(clean.strip())
    except Exception:
        return None


def _load_vix_daily(vix_dir: Path) -> dict[dt.date, float]:
    """Load VIX daily close from vix_5m CSV (last bar of each day)."""
    import glob
    pattern = str(vix_dir / "vix_5m_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        return {}
    vix_by_date: dict[dt.date, float] = {}
    for fpath in files:
        try:
            with open(fpath, encoding="utf-8") as f:
                lines = f.readlines()
            # header line then data
            if len(lines) < 2:
                continue
            header = lines[0].strip().split(",")
            try:
                ts_idx = header.index("timestamp_et")
                close_idx = header.index("close")
            except ValueError:
                continue
            for line in lines[1:]:
                parts = line.strip().split(",")
                if len(parts) <= max(ts_idx, close_idx):
                    continue
                parsed = _parse_bar_ts(parts[ts_idx])
                if parsed is None:
                    continue
                d = parsed.date()
                try:
                    close = float(parts[close_idx])
                    vix_by_date[d] = close  # last bar wins
                except ValueError:
                    pass
        except Exception:
            continue
    return vix_by_date


def _vix_regime(vix: float | None) -> str:
    if vix is None:
        return "unknown"
    if vix < 15:
        return "VIX_LOW (<15)"
    elif vix < 20:
        return "VIX_MODERATE (15-20)"
    elif vix < 25:
        return "VIX_ELEVATED (20-25)"
    else:
        return "VIX_HIGH (ge25)"


def _time_bucket(dt_bar: dt.datetime | None) -> str:
    if dt_bar is None:
        return "unknown"
    h = dt_bar.hour
    m = dt_bar.minute
    slot = (h * 60 + m) // 30  # 30-min buckets
    slot_start = slot * 30
    slot_h = slot_start // 60
    slot_m = slot_start % 60
    return f"{slot_h:02d}:{slot_m:02d}"


def main() -> None:
    print("[v14e_fingerprint] loading observations...")
    lines_raw = OBS_FILE.read_text(encoding="utf-8").splitlines()

    # Load all v14_enhanced bear+high observations
    target_obs: list[dict] = []
    for line in lines_raw:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("watcher_name") != "v14_enhanced_watcher":
            continue
        if r.get("direction") != "short":
            continue
        if r.get("confidence") != "high":
            continue
        if r.get("would_be_pnl_dollars") is None:
            continue
        target_obs.append(r)

    print(f"[v14e_fingerprint] found {len(target_obs)} BEAR_HIGH_CONF obs")

    # Load VIX daily
    vix_by_date = _load_vix_daily(VIX_DIR)
    print(f"[v14e_fingerprint] VIX daily data: {len(vix_by_date)} days")

    # ── Per-observation extraction ─────────────────────────────────────────────
    trigger_counts: Counter = Counter()
    trigger_combo_counts: Counter = Counter()
    time_bucket_counts: Counter = Counter()
    vix_regime_counts: Counter = Counter()
    score_counts: Counter = Counter()
    outcome_counts: Counter = Counter()
    date_counts: Counter = Counter()
    quality_rank_counts: Counter = Counter()

    wins_by_regime: dict[str, list[float]] = defaultdict(list)
    wins_by_time: dict[str, list[float]] = defaultdict(list)

    sample_records = []  # first 10 full records for display

    for obs in target_obs:
        bar_ts = obs.get("bar_timestamp_et", "")
        parsed_ts = _parse_bar_ts(bar_ts)
        bar_date = parsed_ts.date() if parsed_ts else None

        # VIX regime
        vix_close = vix_by_date.get(bar_date) if bar_date else None
        regime = _vix_regime(vix_close)
        vix_regime_counts[regime] += 1
        wins_by_regime[regime].append(obs.get("would_be_pnl_dollars", 0))

        # Time bucket
        tb = _time_bucket(parsed_ts)
        time_bucket_counts[tb] += 1
        wins_by_time[tb].append(obs.get("would_be_pnl_dollars", 0))

        # Date
        if bar_date:
            date_counts[str(bar_date)] += 1
        else:
            date_counts["unknown"] += 1

        # Triggers
        triggers = obs.get("triggers") or []
        if isinstance(triggers, list):
            for t in triggers:
                trigger_counts[str(t)] += 1
            combo = tuple(sorted(str(t) for t in triggers))
            trigger_combo_counts[combo] += 1

        # Outcome
        outcome = obs.get("would_be_outcome") or obs.get("outcome") or "unknown"
        outcome_counts[str(outcome)] += 1

        # Score / quality
        meta = obs.get("metadata") or {}
        score = meta.get("score") or meta.get("bear_score")
        if score is not None:
            score_counts[str(score)] += 1

        quality_rank = obs.get("quality") or obs.get("quality_rank")
        if quality_rank is not None:
            quality_rank_counts[str(quality_rank)] += 1

        # Build sample
        if len(sample_records) < 15:
            sample_records.append({
                "date": str(bar_date) if bar_date else "?",
                "time": parsed_ts.strftime("%H:%M") if parsed_ts else "?",
                "triggers": triggers,
                "outcome": str(outcome),
                "pnl": obs.get("would_be_pnl_dollars"),
                "confidence": obs.get("confidence"),
                "vix_regime": regime,
                "metadata_keys": list(meta.keys())[:8],
                "score": score,
                "quality_rank": quality_rank,
            })

    # ── Regime WR table ──────────────────────────────────────────────────────
    regime_summary: dict[str, dict] = {}
    for reg, pnls in sorted(wins_by_regime.items()):
        wins = sum(1 for p in pnls if p > 0)
        regime_summary[reg] = {
            "n": len(pnls),
            "wins": wins,
            "wr_pct": round(wins / len(pnls) * 100, 1) if pnls else 0,
            "total_pnl": round(sum(pnls), 2),
        }

    # ── Time-bucket WR table ─────────────────────────────────────────────────
    time_summary: dict[str, dict] = {}
    for tb, pnls in sorted(wins_by_time.items()):
        wins = sum(1 for p in pnls if p > 0)
        time_summary[tb] = {
            "n": len(pnls),
            "wins": wins,
            "wr_pct": round(wins / len(pnls) * 100, 1) if pnls else 0,
            "total_pnl": round(sum(pnls), 2),
        }

    # ── Date concentration: how many unique days? ────────────────────────────
    known_dates = [d for d in date_counts if d != "unknown"]
    n_unique_dates = len(known_dates)
    top_dates = date_counts.most_common(5)

    # ── Trigger combo top-10 ─────────────────────────────────────────────────
    top_combos = [
        {"triggers": list(combo), "count": cnt}
        for combo, cnt in trigger_combo_counts.most_common(10)
    ]
    top_triggers = [
        {"trigger": t, "count": cnt}
        for t, cnt in trigger_counts.most_common(15)
    ]

    # ── Print summary ─────────────────────────────────────────────────────────
    print("\n=== V14E BEAR_HIGH_CONF FINGERPRINT ===")
    print(f"  Total: N={len(target_obs)}  WR={sum(1 for o in target_obs if (o.get('would_be_pnl_dollars') or 0) > 0)/len(target_obs)*100:.1f}%  P&L=${sum(o.get('would_be_pnl_dollars',0) for o in target_obs):+,.0f}")
    print(f"\n  VIX Regime breakdown:")
    for reg, s in sorted(regime_summary.items()):
        print(f"    {reg:30s}: N={s['n']:2d}  WR={s['wr_pct']:5.1f}%  P&L=${s['total_pnl']:+,.0f}")
    print(f"\n  Time-of-day breakdown (30-min buckets):")
    for tb, s in sorted(time_summary.items()):
        bar = "#" * s["n"]
        print(f"    {tb}: N={s['n']:2d}  WR={s['wr_pct']:5.1f}%  P&L=${s['total_pnl']:+,.0f}  {bar}")
    print(f"\n  Outcome distribution:")
    for oc, cnt in outcome_counts.most_common():
        print(f"    {str(oc):30s}: {cnt}")
    print(f"\n  Top trigger combos:")
    for item in top_combos[:8]:
        print(f"    {item['triggers']}: {item['count']}")
    print(f"\n  Unique dates: {n_unique_dates} (top-5: {top_dates[:5]})")

    # ── Build output ─────────────────────────────────────────────────────────
    result = {
        "analysis": "V14E BEAR_HIGH_CONF sub-tier fingerprint",
        "n_total": len(target_obs),
        "vix_regime_summary": regime_summary,
        "time_bucket_summary": time_summary,
        "outcome_counts": dict(outcome_counts.most_common()),
        "trigger_individual_counts": dict(trigger_counts.most_common(20)),
        "trigger_combo_top10": top_combos,
        "score_distribution": dict(score_counts),
        "quality_rank_distribution": dict(quality_rank_counts),
        "date_concentration": {
            "n_unique_dates": n_unique_dates,
            "obs_per_date_median": round(
                sorted([v for k, v in date_counts.items() if k != "unknown"])[len(known_dates) // 2], 1
            ) if known_dates else None,
            "top_5_dates": [{"date": d, "count": c} for d, c in top_dates],
            "unknown_count": date_counts.get("unknown", 0),
        },
        "sample_records": sample_records,
    }

    OUT_JSON.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\n[v14e_fingerprint] wrote {OUT_JSON}")

    # ── Markdown report ───────────────────────────────────────────────────────
    total_wins = sum(1 for o in target_obs if (o.get("would_be_pnl_dollars") or 0) > 0)
    total_pnl = sum(o.get("would_be_pnl_dollars", 0) for o in target_obs)

    md = [
        "# V14E BEAR_HIGH_CONF Sub-Tier Fingerprint Analysis",
        f"> Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M ET')}",
        f"> Source: {len(target_obs)} bear+high-confidence v14_enhanced_watcher observations",
        "",
        "## Summary",
        "",
        f"**N={len(target_obs)}  WR={total_wins/len(target_obs)*100:.1f}%  P&L=${total_pnl:+,.0f}**",
        "",
        "The BEAR_HIGH_CONF sub-tier requires `direction=short AND confidence=high` in the",
        "v14_enhanced_watcher. High confidence = `has_confluence AND n_triggers >= 3`.",
        "",
        "## VIX Regime — Is the edge regime-independent?",
        "",
        "| VIX Regime | N | WR% | P&L |",
        "|---|---:|---:|---:|",
    ]
    for reg, s in sorted(regime_summary.items()):
        md.append(f"| {reg} | {s['n']} | {s['wr_pct']}% | ${s['total_pnl']:+,.0f} |")

    md += [
        "",
        "## Time-of-Day Distribution (30-min buckets)",
        "",
        "| Time ET | N | WR% | P&L |",
        "|---|---:|---:|---:|",
    ]
    for tb, s in sorted(time_summary.items()):
        md.append(f"| {tb} | {s['n']} | {s['wr_pct']}% | ${s['total_pnl']:+,.0f} |")

    md += [
        "",
        "## Outcome Distribution",
        "",
        "| Outcome | Count |",
        "|---|---:|",
    ]
    for oc, cnt in outcome_counts.most_common():
        md.append(f"| {oc} | {cnt} |")

    md += [
        "",
        "## Top Trigger Combinations (what makes high confidence?)",
        "",
        "| Trigger combo | Count |",
        "|---|---:|",
    ]
    for item in top_combos[:10]:
        md.append(f"| `{item['triggers']}` | {item['count']} |")

    md += [
        "",
        "## Individual Trigger Frequency",
        "",
        "| Trigger | Count |",
        "|---|---:|",
    ]
    for item in top_triggers[:15]:
        md.append(f"| `{item['trigger']}` | {item['count']} |")

    md += [
        "",
        "## Date Concentration",
        "",
        f"Unique dates with observations: **{n_unique_dates}**",
        f"Unknown (timestamp parse fail): {date_counts.get('unknown', 0)}",
        "",
        "Top-5 dates by observation count:",
        "",
        "| Date | N |",
        "|---|---:|",
    ]
    for d, c in top_dates:
        md.append(f"| {d} | {c} |")

    md += [
        "",
        "## Implications for V14E Promotion Path",
        "",
        "- If WR ≥ 80% holds across ≥2 VIX regimes → regime-independent edge confirmed",
        "- If time-of-day shows strong concentration → gate by entry window",
        "- If trigger combos cluster around 2-3 patterns → the 'high confidence' gate",
        "  is already capturing a real structural signal, not randomness",
        "- Promotion gate proposal: BEAR_HIGH_CONF watch-only → N_target=50 obs, WR≥75%",
        "  This is faster than the full BEAR_ONLY path (N_target=100, WR≥55%)",
        "  because the 84.8% WR with n=33 already provides strong signal",
    ]

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"[v14e_fingerprint] wrote {OUT_MD}")


if __name__ == "__main__":
    main()
