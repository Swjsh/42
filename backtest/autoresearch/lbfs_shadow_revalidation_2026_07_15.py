"""LBFS shadow-wiring revalidation (2026-07-15).

Pre-registered in analysis/recommendations/lbfs-shadow-wiring-preregistration.json
BEFORE this script was run. Two candidates, combined for the final read:

  C1 -- re-run the EXISTING 19-signal VIX>=20 ATM/OTM-1 cohort (2026-05-24's
        lbfs_expanded_real_fills.py signal set, reloaded from the watcher-observations
        rotation archives since the live 2026-06-22 rotation moved them out of the
        current file) through TODAY's simulate_trade_real, to check whether the prior
        result still holds under any exit-mechanism drift since 2026-05-24.
  C2 -- extend the watcher's own v2 scan (MIN_SPREAD_MIXED_CENTS=12, matching the
        shipped watcher) over 2026-05-16..2026-07-14 -- the window the original
        16-month scan never covered (its SPY_PATH was capped at 2026-05-15) -- to find
        any NEW VIX>=20 qualifying signals, then real-fills-grade them identically.

Output: analysis/recommendations/lbfs-shadow-wiring-revalidation-2026-07-15.json
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent   # backtest/
ROOT = REPO.parent                              # repo root
sys.path.insert(0, str(REPO))

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.level_break_first_strike_scan import (  # noqa: E402
    scan as lbfs_scan,
    MIN_SPREAD_MIXED_CENTS as _V1_MIN_SPREAD,  # unused directly; scan() reads the module global
)
import autoresearch.level_break_first_strike_scan as lbfs_scan_mod  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stdout, encoding="utf-8")
log = logging.getLogger(__name__)

STATE_DIR = ROOT / "automation" / "state"
ARCHIVE_DIR = STATE_DIR / "archive"
PREREG = ROOT / "analysis" / "recommendations" / "lbfs-shadow-wiring-preregistration.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "lbfs-shadow-wiring-revalidation-2026-07-15.json"

VIX_HIGH_THRESHOLD = 20.0
EXTENSION_START = dt.date(2026, 5, 16)   # first day the original 16-month scan never covered
EXTENSION_END = dt.date(2026, 7, 14)     # latest cached SPY 5m data
LOOKBACK_BUFFER_START = dt.date(2026, 4, 1)  # extra history so level/ribbon warmup is real


# --------------------------------------------------------------------------- #
# C1 -- reload the archived 19-signal VIX>=20 cohort
# --------------------------------------------------------------------------- #

def load_archived_vix20_lbfs_observations() -> list[dict]:
    rows = []
    for path in [
        ARCHIVE_DIR / "watcher-observations-rotated-2026-06-22.jsonl",
        ARCHIVE_DIR / "watcher-observations-autoheal-20260707-142054.jsonl",
        STATE_DIR / "watcher-observations.jsonl",   # current file too, in case it has any
    ]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("watcher_name") != "level_break_first_strike_watcher":
                continue
            if r.get("confidence") != "high":  # VIX>=20 = "high"
                continue
            if r.get("would_be_outcome") == "watch_only_registration":
                continue  # the one-time registration marker, not a real signal
            rows.append(r)

    seen: set = set()
    deduped = []
    for r in rows:
        key = (r.get("bar_timestamp_et") or "")[:16]
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return sorted(deduped, key=lambda r: (r.get("bar_timestamp_et") or ""))


# --------------------------------------------------------------------------- #
# C2 -- extension scan 2026-05-16..2026-07-14
# --------------------------------------------------------------------------- #

def run_extension_scan() -> list[dict]:
    """Run the watcher's own v2 scan (MIN_SPREAD_MIXED_CENTS=12) over the extension
    window, using cached SPY/VIX data with a lookback buffer for warmup. Returns
    VIX>=20 signals only, restricted to EXTENSION_START..EXTENSION_END."""
    spy_full = pd.read_csv(REPO / "data" / "spy_5m_2025-01-01_2026-07-14.csv")
    vix_a = pd.read_csv(REPO / "data" / "vix_5m_2025-01-01_2026-07-08.csv")
    vix_b = pd.read_csv(REPO / "data" / "vix_5m_2026-05-19_2026-07-15.csv")

    spy_full["_ts"] = pd.to_datetime(spy_full["timestamp_et"], utc=True).dt.tz_convert(
        "America/New_York").dt.tz_localize(None)
    vix_a["_ts"] = pd.to_datetime(vix_a["timestamp_et"], utc=True).dt.tz_convert(
        "America/New_York").dt.tz_localize(None)
    vix_b["_ts"] = pd.to_datetime(vix_b["timestamp_et"], utc=True).dt.tz_convert(
        "America/New_York").dt.tz_localize(None)

    vix_full = pd.concat(
        [vix_a[vix_a["_ts"] <= "2026-07-08 23:59:59"], vix_b[vix_b["_ts"] > "2026-07-08 23:59:59"]],
        ignore_index=True,
    ).drop(columns="_ts").sort_values("timestamp_et").reset_index(drop=True)

    spy_window = spy_full[
        (spy_full["_ts"].dt.date >= LOOKBACK_BUFFER_START) & (spy_full["_ts"].dt.date <= EXTENSION_END)
    ].drop(columns="_ts").reset_index(drop=True)

    log.info("Extension scan: %d SPY bars (%s buffer start .. %s), v2 params (MIN_SPREAD=12c)",
             len(spy_window), LOOKBACK_BUFFER_START, EXTENSION_END)

    # v2 params: MIN_SPREAD_MIXED_CENTS=12 (guard-rail fix), matching the SHIPPED watcher's
    # MIN_SPREAD_MIXED_CENTS constant (level_break_first_strike_watcher.py:62).
    lbfs_scan_mod.MIN_SPREAD_MIXED_CENTS = 12
    lbfs_scan_mod.SCAN_START = LOOKBACK_BUFFER_START

    result = lbfs_scan(spy_window, vix_full)
    all_signals = result["signals"]
    # Restrict to the genuinely-new window + VIX>=20 (the ratifiable regime).
    new_signals = [
        s for s in all_signals
        if EXTENSION_START.isoformat() <= s["date"] <= EXTENSION_END.isoformat()
        and s["vix_now"] >= VIX_HIGH_THRESHOLD
    ]
    log.info("Extension scan: %d total signals in window, %d VIX>=20",
             len([s for s in all_signals if EXTENSION_START.isoformat() <= s["date"] <= EXTENSION_END.isoformat()]),
             len(new_signals))
    return new_signals


def _extension_signal_to_obs(s: dict) -> dict:
    """Adapt an extension-scan signal row into the same shape run_signal() expects
    from a watcher-observations.jsonl row (bar_timestamp_et, entry_price, metadata)."""
    return {
        "bar_timestamp_et": f"{s['date']}T{s['time']}",
        "entry_price": s["bar_close"],
        "would_be_outcome": "win" if s["win"] else "loss",
        "would_be_pnl_dollars": None,
        "metadata": {
            "break_level": s["level"],
            "vix_now": s["vix_now"],
            "break_below_cents": round(s["break_below"] * 100, 1),
            "vol_ratio": s["vol_mult"],
        },
    }


# --------------------------------------------------------------------------- #
# Real-fills grading (mirrors lbfs_expanded_real_fills.py::run_signal exactly)
# --------------------------------------------------------------------------- #

def run_signal(obs: dict, strike_offset: int = 0) -> dict:
    ts_raw = obs.get("bar_timestamp_et", "")
    ts_date = ts_raw[:10]
    entry_price = obs.get("entry_price", 0.0)
    stop_price = obs.get("stop_price", entry_price + 0.30)
    meta = obs.get("metadata") or {}
    break_level = meta.get("break_level", stop_price - 0.30)
    vix_now = meta.get("vix_now", 0.0)
    break_below_cents = meta.get("break_below_cents", 0.0)
    vol_ratio = meta.get("vol_ratio", 0.0)

    result = {
        "date": ts_date, "bar_timestamp_et": ts_raw[:16], "entry_price": entry_price,
        "break_level": break_level, "break_below_cents": break_below_cents,
        "vol_ratio": vol_ratio, "vix_now": vix_now, "strike_offset": strike_offset,
        "real_fills_pnl": None, "real_fills_outcome": None, "error": None,
    }

    try:
        d = dt.date.fromisoformat(ts_date)
    except ValueError:
        result["error"] = f"bad date {ts_date}"
        return result

    d_start = d - dt.timedelta(days=5)
    try:
        spy_full, _ = ar_runner.load_data(d_start, d)
    except Exception:
        try:
            spy_full, _ = ar_runner.load_data(d, d)
        except Exception as e2:
            result["error"] = f"load_data failed: {e2}"
            return result

    ts_col = pd.to_datetime(spy_full["timestamp_et"])
    if getattr(ts_col.dt, "tz", None) is not None:
        ts_col = ts_col.dt.tz_convert("America/New_York").dt.tz_localize(None)
    spy_full = spy_full.copy()
    spy_full["timestamp_et"] = ts_col

    target_date = d
    day_mask = spy_full["timestamp_et"].dt.date == target_date
    spy_day = spy_full[day_mask & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))].copy()
    if spy_day.empty:
        result["error"] = f"no day bars for {ts_date}"
        return result

    first_day_ts = spy_day["timestamp_et"].iloc[0]
    prior_bars = spy_full[spy_full["timestamp_et"] < first_day_ts].tail(40).copy()
    combined = pd.concat([prior_bars, spy_day], ignore_index=True)

    try:
        ribbon_df = compute_ribbon(combined["close"]).reset_index(drop=True)
    except Exception as e:
        result["error"] = f"ribbon compute failed: {e}"
        return result

    entry_ts = pd.to_datetime(ts_raw[:16])
    if entry_ts.tz is not None:
        entry_ts = entry_ts.tz_localize(None)

    matches = combined[combined["timestamp_et"] == entry_ts]
    if matches.empty:
        diff = (combined["timestamp_et"] - entry_ts).dt.total_seconds().abs()
        if diff.min() <= 600:
            closest = int(diff.idxmin())
            matches = combined.iloc[[closest]]
    if matches.empty:
        result["error"] = f"entry bar not found for {ts_raw[:16]}"
        return result

    entry_bar_idx = int(matches.index[0])
    entry_bar = combined.iloc[entry_bar_idx]

    try:
        fill = simulate_trade_real(
            entry_bar_idx=entry_bar_idx, entry_bar=entry_bar, spy_df=combined,
            ribbon_df=ribbon_df, rejection_level=float(break_level),
            triggers_fired=["MIXED_RIBBON_LEVEL_BREAK", "VOL_1.5X"], side="P", qty=3,
            setup="LEVEL_BREAK_FIRST_STRIKE", premium_stop_pct=-0.99,
            strike_offset=strike_offset,
        )
    except Exception as e:
        result["error"] = f"simulate_trade_real failed: {e}"
        return result

    if fill is None:
        result["error"] = "simulate_trade_real returned None (no OPRA data?)"
        return result

    pnl = fill.dollar_pnl or 0
    result["real_fills_pnl"] = round(pnl, 2)
    result["real_fills_outcome"] = fill.exit_reason
    result["entry_premium"] = round(fill.entry_premium or 0, 4)
    log.info("  %s VIX=%.1f break=%.0fc pnl=$%+.0f exit=%s",
             ts_raw[:16], vix_now, break_below_cents, pnl, fill.exit_reason)
    return result


# --------------------------------------------------------------------------- #
# WF / sub-window / pass-bar (per the frozen prereg)
# --------------------------------------------------------------------------- #

def _walk_forward(graded_sorted: list[dict]) -> dict:
    n = len(graded_sorted)
    if n < 2:
        return {"wf_ratio": None, "is_pnl": None, "oos_pnl": None, "note": "n<2, WF undefined"}
    mid = (n + 1) // 2  # IS gets the extra signal on odd N
    is_rows, oos_rows = graded_sorted[:mid], graded_sorted[mid:]
    is_pnl = sum(r["real_fills_pnl"] for r in is_rows)
    oos_pnl = sum(r["real_fills_pnl"] for r in oos_rows)
    if is_pnl <= 0:
        return {"wf_ratio": None, "is_pnl": round(is_pnl, 2), "oos_pnl": round(oos_pnl, 2),
                "note": "undefined (IS non-positive)"}
    return {"wf_ratio": round(oos_pnl / is_pnl, 4), "is_pnl": round(is_pnl, 2),
            "oos_pnl": round(oos_pnl, 2), "note": None}


def _sub_window_stability(graded_sorted: list[dict]) -> dict:
    n = len(graded_sorted)
    if n < 3:
        return {"stable": None, "thirds_pnl": [], "n_hurt": None, "note": "n<3, undefined"}
    k = n // 3
    thirds = [graded_sorted[:k], graded_sorted[k:2 * k], graded_sorted[2 * k:]]
    thirds_pnl = [round(sum(r["real_fills_pnl"] for r in t), 2) for t in thirds]
    n_hurt = sum(1 for p in thirds_pnl if p < 0)
    return {"stable": n_hurt <= 1, "thirds_pnl": thirds_pnl, "n_hurt": n_hurt, "note": None}


def main() -> int:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "FROZEN_PENDING_RUN", "prereg must be frozen before running"

    # ---- C1: reload + re-grade the existing 19-signal cohort ----
    c1_obs = load_archived_vix20_lbfs_observations()
    log.info("C1: loaded %d archived VIX>=20 LBFS observations", len(c1_obs))
    c1_results = []
    for strike_offset in (0, 1):
        for obs in c1_obs:
            r = run_signal(obs, strike_offset=strike_offset)
            r["strike_offset_label"] = "ATM" if strike_offset == 0 else "OTM-1"
            r["source"] = "C1_existing_cohort"
            c1_results.append(r)

    # ---- C2: extension scan + grade any new signals ----
    c2_signals = run_extension_scan()
    c2_obs = [_extension_signal_to_obs(s) for s in c2_signals]
    c2_results = []
    for strike_offset in (0, 1):
        for obs in c2_obs:
            r = run_signal(obs, strike_offset=strike_offset)
            r["strike_offset_label"] = "ATM" if strike_offset == 0 else "OTM-1"
            r["source"] = "C2_extension_scan"
            c2_results.append(r)

    all_results = c1_results + c2_results

    # ---- Combined summary per strike tier ----
    summary = {}
    for label in ("ATM", "OTM-1"):
        subset = [r for r in all_results if r["strike_offset_label"] == label]
        graded = [r for r in subset if r.get("real_fills_pnl") is not None]
        wins = [r for r in graded if r["real_fills_pnl"] > 0]
        total_pnl = sum(r["real_fills_pnl"] for r in graded)
        wr = len(wins) / len(graded) if graded else 0
        summary[label] = {
            "n_total": len(subset), "n_graded": len(graded),
            "n_no_data": sum(1 for r in subset if r.get("error")),
            "wins": len(wins), "losses": len(graded) - len(wins),
            "win_rate": round(wr, 4), "total_pnl": round(total_pnl, 2),
            "op21_gate_pass": bool(wr >= 0.50 and total_pnl > 0),
        }

    # ---- Ratification read: ATM combined cohort only, per the frozen prereg ----
    atm_graded = sorted(
        [r for r in all_results if r["strike_offset_label"] == "ATM" and r.get("real_fills_pnl") is not None],
        key=lambda r: r["bar_timestamp_et"],
    )
    wf = _walk_forward(atm_graded)
    subwin = _sub_window_stability(atm_graded)
    oos_positive = (wf["oos_pnl"] is not None and wf["oos_pnl"] > 0)
    wf_pass = (wf["wf_ratio"] is not None and wf["wf_ratio"] >= 0.70)
    subwin_pass = bool(subwin["stable"])
    anchor_no_regression = True  # by construction -- see prereg anchor_day_check.consequence
    n_advisory_pass = len(atm_graded) >= 15

    hard_components = {
        "oos_positive": oos_positive, "wf_ge_070": wf_pass,
        "sub_window_stable": subwin_pass, "anchor_no_regression": anchor_no_regression,
    }
    all_hard_pass = all(hard_components.values())
    verdict = "RATIFY_STUDY_CLEARS_BAR" if all_hard_pass else "STUDY_FAILS_BAR_SHIP_SHADOW_ONLY_REGARDLESS"

    output = {
        "generated_at": dt.datetime.now().isoformat(),
        "prereg_file": str(PREREG.relative_to(ROOT)),
        "description": "LBFS shadow-wiring revalidation -- C1 (re-run existing 19-signal VIX>=20 cohort through today's simulator) + C2 (extension scan 2026-05-16..2026-07-14 for new signals)",
        "c1_n_observations": len(c1_obs),
        "c2_n_new_signals_found": len(c2_obs),
        "summary_by_strike": summary,
        "ratification_read_atm_combined": {
            "n_graded": len(atm_graded),
            "walk_forward": wf,
            "sub_window_stability": subwin,
            "hard_components": hard_components,
            "n_advisory_ge_15": n_advisory_pass,
            "verdict": verdict,
        },
        "all_signals": all_results,
    }

    OUT_JSON.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    log.info("\n=== FINAL VERDICT: %s ===", verdict)
    log.info("ATM combined: N=%d graded=%d WR=%.1f%% P&L=$%+.2f",
             summary["ATM"]["n_total"], summary["ATM"]["n_graded"],
             summary["ATM"]["win_rate"] * 100, summary["ATM"]["total_pnl"])
    log.info("WF: %s | sub_window: %s | hard_components: %s", wf, subwin, hard_components)
    log.info("Output: %s", OUT_JSON)
    return 0


if __name__ == "__main__":
    sys.exit(main())
