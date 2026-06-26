"""Task 3.3 — VIX-character-aware level confidence (L73).

QUESTION: Do levels respect at materially different rates in VIX-trending vs
VIX-spike-and-revert regimes? If yes, propose a regime-confidence multiplier
that improves the engine's level selection in high-vol environments.

L73 FINDING (already validated on SNIPER watcher):
  VIX level alone (>= 18) insufficient — VIX CHARACTER (trending/escalating vs
  spike-and-revert) is the true discriminator.
  Joint condition: VIX >= 18 AND VIX > 5-day-avg → strong regime signal.
  This was validated OOS for SNIPER with WF=0.983 but NOT for general level quality.

METHOD:
  For each of the 219 benchmark days, compute:
    - VIX classification: low (<15), mid (15-25), high (>25)
    - VIX character: trending (today's VIX > 5d rolling avg VIX) vs spike-revert
  Then cross-tabulate respect-rate by (VIX class × VIX character).

  IS/OOS validation: 50/50 split (IS = days 1-110, OOS = days 111-219).
  Walk-forward ratio: OOS/IS respect-lift differential vs DM-null.

OP-20 disclosure:
  N = 219 days split 50/50 IS/OOS.
  Metric: respect-rate-of-touched vs DM-null (pp lift).
  SPY price-space only (L74). VIX proxy = VIX index from CSV.

Output:
  analysis/level-quality/regime_level_results.json
  strategy/candidates/2026-06-15-regime-levels.md   (DRAFT)
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "backtest" / "data"
OUT_DIR = REPO / "analysis" / "level-quality"
CANDIDATES_DIR = REPO / "strategy" / "candidates"
CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)

VIX_FILES = [
    "vix_5m_2025-01-01_2026-05-22.csv",
    "vix_5m_2025-01-01_2025-05-31.csv",
    "vix_5m_2026-05-19_2026-06-15.csv",
]

VIX_5D_WINDOW = 5     # days for VIX rolling average (per L73 — 5 days uniquely optimal)
VIX_HIGH_THRESH = 25
VIX_LOW_THRESH = 15


def _import_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


levels_mod = _import_mod("gamma_levels", REPO / "backtest" / "lib" / "levels.py")
bench_mod = _import_mod("bench_lq", REPO / "analysis" / "level-quality" / "benchmark_level_quality.py")

classify_level = bench_mod.classify_level
tag_source = bench_mod.tag_source
HEADLINE_REACT = bench_mod.HEADLINE_REACT
HEADLINE_K = bench_mod.HEADLINE_K
RTH_OPEN = bench_mod.RTH_OPEN
RTH_CLOSE = bench_mod.RTH_CLOSE
START_DAY = bench_mod.START_DAY
SPY_FILES = bench_mod.SPY_FILES


def _parse_wall_clock(s):
    return pd.to_datetime(s.astype(str).str.slice(0, 19), format="%Y-%m-%d %H:%M:%S")


def load_spy():
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
    for c in ("open", "high", "low", "close"):
        spy[c] = pd.to_numeric(spy[c], errors="coerce")
    spy["date"] = spy["timestamp_et"].dt.date
    spy["time"] = spy["timestamp_et"].dt.time
    return spy.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def load_vix():
    """Load VIX data and return daily close values."""
    frames = []
    for fn in VIX_FILES:
        p = DATA_DIR / fn
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["timestamp_et"] = _parse_wall_clock(df["timestamp_et"])
        for c in ("open", "high", "low", "close"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    vix = pd.concat(frames, ignore_index=True)
    vix = vix.drop_duplicates(subset=["timestamp_et"]).sort_values("timestamp_et").reset_index(drop=True)
    vix["date"] = vix["timestamp_et"].dt.date
    vix["time"] = vix["timestamp_et"].dt.time

    # Get daily close: last RTH bar's close
    rth_mask = (vix["time"] >= RTH_OPEN) & (vix["time"] < RTH_CLOSE)
    daily = vix[rth_mask].groupby("date")["close"].last().reset_index()
    daily.columns = ["date", "vix_close"]
    daily = daily.sort_values("date").reset_index(drop=True)
    return daily


def compute_vix_character(daily_vix: pd.DataFrame) -> dict:
    """For each date, compute VIX level class and trending/spike-revert character.

    Returns: {date: {vix_close, vix_class, vix_5d_avg, vix_trending}}
    """
    result = {}
    dates = sorted(daily_vix["date"].unique())
    for i, d in enumerate(dates):
        vix_val = float(daily_vix[daily_vix["date"] == d]["vix_close"].iloc[0])
        # 5-day trailing average (excluding today)
        prior_dates = [x for x in dates[:i] if x < d][-VIX_5D_WINDOW:]
        if len(prior_dates) >= 3:
            prior_vix = daily_vix[daily_vix["date"].isin(prior_dates)]["vix_close"].mean()
            vix_trending = vix_val > prior_vix
        else:
            prior_vix = None
            vix_trending = None

        if vix_val >= VIX_HIGH_THRESH:
            vix_class = "high"
        elif vix_val >= VIX_LOW_THRESH:
            vix_class = "mid"
        else:
            vix_class = "low"

        result[d] = {
            "vix_close": round(vix_val, 2),
            "vix_class": vix_class,
            "vix_5d_avg": round(float(prior_vix), 2) if prior_vix else None,
            "vix_trending": vix_trending,
        }
    return result


def blank_acc():
    return {"n": 0, "touched": 0, "respect": 0}


def main():
    spy = load_spy()
    print(f"Loaded {len(spy):,} SPY bars")

    daily_vix = load_vix()
    if daily_vix.empty:
        print("WARNING: No VIX data found. Exiting.")
        return
    print(f"Loaded {len(daily_vix)} VIX daily closes")

    vix_char = compute_vix_character(daily_vix)
    print(f"VIX character computed for {len(vix_char)} days")

    all_days = sorted(d for d in spy["date"].unique() if d >= START_DAY)
    dm_null_respect = bench_mod.load_benchmark_dm_null_respect() if hasattr(bench_mod, "load_benchmark_dm_null_respect") else 0.2568

    # Regime accumulators: keyed by (vix_class, vix_trending_bool)
    regime_accs: dict[str, dict] = {}
    # IS/OOS: days 1-110 = IS, 111-219 = OOS
    is_oos_accs: dict[str, dict[str, dict]] = {"IS": {}, "OOS": {}}

    days_done = 0
    n_no_vix = 0

    for d in all_days:
        open_mask = (spy["date"] == d) & (spy["time"] >= RTH_OPEN)
        if not open_mask.any():
            continue
        open_idx = int(np.argmax(open_mask.to_numpy()))
        history = spy.iloc[:open_idx]
        if history["date"].nunique() < 6:
            continue

        vc = vix_char.get(d)
        if vc is None or vc["vix_trending"] is None:
            n_no_vix += 1
            days_done += 1
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
        if len(rth) < 6:
            continue
        rth = rth.reset_index(drop=True)

        vix_class = vc["vix_class"]
        trending = vc["vix_trending"]
        regime_key = f"{vix_class}_{'trending' if trending else 'spike'}"
        split = "IS" if days_done < 110 else "OOS"

        if regime_key not in regime_accs:
            regime_accs[regime_key] = blank_acc()
        if regime_key not in is_oos_accs["IS"]:
            is_oos_accs["IS"][regime_key] = blank_acc()
            is_oos_accs["OOS"][regime_key] = blank_acc()

        for L in active:
            src = tag_source(L, multi, swept)
            o = classify_level(L, rth, HEADLINE_REACT, HEADLINE_K, src, vix_class)

            regime_accs[regime_key]["n"] += 1
            is_oos_accs[split][regime_key]["n"] += 1
            if o.touched:
                regime_accs[regime_key]["touched"] += 1
                is_oos_accs[split][regime_key]["touched"] += 1
                if o.kind == "RESPECT":
                    regime_accs[regime_key]["respect"] += 1
                    is_oos_accs[split][regime_key]["respect"] += 1

        days_done += 1

    print(f"\nDays processed: {days_done} (skipped {n_no_vix} without VIX)")
    print(f"\n{'Regime':<20} {'N':>6} {'Touch%':>8} {'Resp%':>8} {'DM-lift':>9}")
    print("-" * 55)

    summary = {}
    for regime_key, acc in sorted(regime_accs.items()):
        n, t, r = acc["n"], acc["touched"], acc["respect"]
        touch_r = round(t / n, 4) if n else None
        resp_r = round(r / t, 4) if t else None
        lift = round((resp_r - dm_null_respect) * 100, 1) if resp_r else None
        print(f"{regime_key:<20} {n:>6} {(touch_r or 0):.1%} {(resp_r or 0):.1%} "
              f"{f'{lift:+.1f}pp' if lift else 'n/a':>9}")
        summary[regime_key] = {
            "n": n, "touched": t, "respect": r,
            "touch_rate": touch_r, "respect_rate": resp_r,
            "dm_null_lift_pp": lift,
        }

    # WF ratio: OOS-lift / IS-lift per regime
    print(f"\n{'Regime':<20} {'IS-lift':>9} {'OOS-lift':>9} {'WF-ratio':>10}")
    print("-" * 52)
    wf_results = {}
    for regime_key in sorted(regime_accs.keys()):
        is_acc = is_oos_accs["IS"].get(regime_key, blank_acc())
        oos_acc = is_oos_accs["OOS"].get(regime_key, blank_acc())
        is_resp = round(is_acc["respect"] / is_acc["touched"], 4) if is_acc["touched"] else None
        oos_resp = round(oos_acc["respect"] / oos_acc["touched"], 4) if oos_acc["touched"] else None
        is_lift = round((is_resp - dm_null_respect) * 100, 1) if is_resp else None
        oos_lift = round((oos_resp - dm_null_respect) * 100, 1) if oos_resp else None
        wf = round(oos_lift / is_lift, 3) if (is_lift and oos_lift and is_lift != 0) else None
        print(f"{regime_key:<20} {f'{is_lift:+.1f}pp' if is_lift else 'n/a':>9} "
              f"{f'{oos_lift:+.1f}pp' if oos_lift else 'n/a':>9} "
              f"{f'{wf:.3f}' if wf else 'n/a':>10}")
        wf_results[regime_key] = {
            "is_respect": is_resp, "oos_respect": oos_resp,
            "is_lift": is_lift, "oos_lift": oos_lift, "wf_ratio": wf,
        }

    # Identify regimes with large respect spread (> 3pp)
    lift_values = [v["dm_null_lift_pp"] for v in summary.values() if v["dm_null_lift_pp"] is not None]
    spread = round(max(lift_values) - min(lift_values), 1) if lift_values else None
    separates = bool(spread and spread > 3.0)

    print(f"\nMax regime spread: {spread}pp {'(SEPARATES at >3pp)' if separates else '(below 3pp threshold)'}")

    # Write JSON
    result = {
        "study": "regime_level_quality",
        "days": days_done,
        "dm_null_respect": dm_null_respect,
        "vix_5d_window": VIX_5D_WINDOW,
        "regime_summary": summary,
        "wf_results": wf_results,
        "max_regime_spread_pp": spread,
        "separates": separates,
    }
    out_json = OUT_DIR / "regime_level_results.json"
    out_json.write_text(json.dumps(result, indent=2))
    print(f"Wrote {out_json}")

    # DRAFT candidate
    best_regime = max(summary.items(), key=lambda kv: kv[1]["dm_null_lift_pp"] or -99)
    worst_regime = min(summary.items(), key=lambda kv: kv[1]["dm_null_lift_pp"] or 99)

    def _lift(x):
        return f"{x:+.1f}pp" if x is not None else "n/a"

    def _wf(x):
        return f"{x:.3f}" if x is not None else "n/a"

    regime_rows = "\n".join(
        "| {} | {} | {:.1%} | {:.1%} | {} |".format(
            k, v["n"], v.get("touch_rate", 0), v.get("respect_rate", 0),
            _lift(v["dm_null_lift_pp"])
        )
        for k, v in sorted(summary.items())
    )

    wf_rows = "\n".join(
        "| {} | {} | {} | {} |".format(k, _lift(v["is_lift"]), _lift(v["oos_lift"]), _wf(v["wf_ratio"]))
        for k, v in sorted(wf_results.items())
    )

    draft_md = f"""# DRAFT: VIX-Character Regime x Level Confidence (L73)

**Status:** DRAFT
**Date:** 2026-06-15
**Verdict:** {"SEPARATES -- regime-confidence multiplier proposed" if separates else "DOES_NOT_SEPARATE -- regime lift spread below 3pp threshold"}
**Auto-ship gate:** FAIL (requires J ratification + A/B scorecard)

## Summary

Do levels respect at materially different rates in VIX-trending vs VIX-spike regimes?

Max regime spread: **{spread}pp** (threshold: >3pp for significance).

VIX character: `trending` = today's VIX > 5-day rolling average (per L73, uniquely optimal window).

## Results

| Regime | N levels | Touch rate | Respect rate | DM-null lift |
|---|---|---|---|---|
{regime_rows}

## IS/OOS Validation (50/50 split)

| Regime | IS lift | OOS lift | WF ratio |
|---|---|---|---|
{wf_rows}

## Key Findings

Best regime:  **{best_regime[0]}** (lift = {best_regime[1].get('dm_null_lift_pp', 'n/a'):+.1f}pp)
Worst regime: **{worst_regime[0]}** (lift = {worst_regime[1].get('dm_null_lift_pp', 'n/a'):+.1f}pp)

{"**SEPARATES**: Regime spread exceeds 3pp. VIX character provides actionable level confidence signal." if separates else "**DOES NOT SEPARATE**: Regime spread below 3pp. VIX character does not reliably predict level quality at the $0.30 respect threshold. The L73 finding (VIX-character as regime filter) was validated for SNIPER entries specifically but does NOT generalize to level quality broadly."}

## Recommendation

{"Propose regime-confidence multiplier: levels in trending-high-VIX days get lower confidence weights (reduced size); levels in spike-revert-high-VIX days get higher confidence. Implement as `level_confidence_multiplier` in params.json after A/B scorecard + anchor-no-regression." if separates else "No regime multiplier needed. Keep the L73 filter as SNIPER-specific (do not apply broadly to level quality). The classification by VIX character is already in the heartbeat for SNIPER watcher. Do not extend to the general level-drawing algorithm."}

## OP-20 Disclosure

- N: {days_done} days, IS/OOS split 50/50 (~110/110)
- Metric: respect-rate-of-touched vs DM-null ({dm_null_respect:.4f})
- VIX character: trending = VIX_today > VIX_5d_avg (per L73 5-day window)
- SPY price-space only (L74)
- WF ratio = OOS_lift / IS_lift (L73 guard: must be > 0.5 for OOS validity)
"""
    draft_path = CANDIDATES_DIR / "2026-06-15-regime-levels.md"
    draft_path.write_text(draft_md, encoding="utf-8")
    print(f"Wrote DRAFT: {draft_path}")


if __name__ == "__main__":
    main()
