"""RRW-AS-VETO-STUDY — does bear RIBBON_REJECTION_WICK improve the LIVE bull path?

Queue item: automation/overnight/queue.md RRW-AS-VETO-STUDY (filed 2026-07-02 after-close).
RIBBON_REJECTION_WICK as an ENTRY signal is KILLED (0/24 BH-FDR survivors, see
analysis/recommendations/ribbon-rejection-wick.json) — but the detector demonstrably SEES
real rejections (anchor case PASS: fired 10:25/10:30/10:40 ET on 2026-07-02, right before
the 10:19 fleet ENTER_BULLs that premium-stopped 3 min later that same session). This is a
DIFFERENT question from "is it a tradeable entry": does a bear-wick firing carry USABLE
information as a defensive OVERLAY on the (already-live) BULLISH_RECLAIM_RIDE_THE_RIBBON
path — either (a) veto a fresh bull entry, or (b) tighten/exit an open bull runner?

METHOD (real fills only — C1 is the only WR authority; no Black-Scholes):
  1. BULL TRADE POPULATION: the PRODUCTION orchestrator (lib.orchestrator.run_backtest,
     use_real_fills=True, enable_bullish=True) with the two already-RATIFIED bull gates
     (block_bull_ribbon_flip 2026-06-17, block_bull_1100_1200 2026-06-18) — i.e. PROD_GATED,
     what the engine actually trades today — at ATM strike (the live core Safe-2 tier per
     the 2026-07-11 strike-tier reconciliation), chart-stop-primary (premium_stop_pct_bull=
     None). Window = the RRW battery's own window (2025-01-02..2026-07-01, OPRA-covered).
  2. BEAR EVENTS: reuse the EXISTING cached superset scan
     (backtest/autoresearch/_state/ribbon_rejection_wick_events.jsonl — same detector, same
     window, produced by ribbon_rejection_wick_battery.py; not re-derived) filtered to
     direction=="short" (bear side only — the veto/tighten signal for a BULL position).
  3. TWO PRE-REGISTERED bear-event configs (chosen from the existing RRWParams dataclass +
     the FAIL scorecard's OWN doc-string BEFORE this study ran — not cherry-picked after
     seeing results):
       A. RRWParams() literal defaults — wick_frac_min=0.35, break_lookback_bars=12,
          vol_mult_min=0 (off), require_stack_not_flipped=True.
       B. Same + vol_mult_min=1.5 — the value ribbon_rejection_wick_detector.py's own
          docstring calls out as "keeps today's anchor" (J's live 2026-07-02 read had
          vol ratio 1.8x).
  4. VETO test: for each bull trade, did a qualifying bear event fire in the window
     [entry_time - 30min, entry_time) on the SAME calendar day? 30 min is this rule_id's
     OWN spec_origin framing ("30 min before the confirmatory ribbon flip"), not invented
     for this study. If so: counterfactual = skip the trade entirely (real dollar_pnl of
     that trade removed from the aggregate).
  5. TIGHTEN test: for each bull trade, did a qualifying bear event fire strictly between
     entry_time and the trade's actual runner_exit_time? If so: counterfactual = exit the
     WHOLE position (not partial-fill-aware — disclosed approximation, see CAVEATS) at the
     option contract's real OPRA bar closest at/after that bear-event bar (next available
     print, mirroring the "entry = next bar" convention used everywhere else in this repo),
     looked up via lib.option_pricing_real.load_contract_bars/option_symbol on the trade's
     OWN strike/side (real fills, not synthetic).
  6. Ship ONE scorecard to analysis/recommendations/rrw-bull-veto-overlay.json regardless
     of verdict (OP-16 disclosure — CLEARS or FAIL, no cherry-picking which number to report).

CAVEATS (disclosed, not hidden — OP-20):
  - TIGHTEN counterfactual treats the WHOLE trade as one block (ignores TP1 partial fills /
    tp1_qty_fraction). This makes it a DIRECTIONAL indicator of whether early-warning bear
    information has value, not a production-ready dollar estimate — a real wiring proposal
    would need a partial-fill-aware replay (same caveat class as tonight's
    EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT counterfactual).
  - A trade can be BOTH veto-flagged and tighten-flagged (an early bear wick that recurs
    during the hold) — the two tests are reported SEPARATELY (mutually exclusive
    application), not stacked, to keep each counterfactual legible.
  - No live wiring happens from this study regardless of verdict — a CLEARS result still
    needs a separate ratification pass (rail 4: guard test + revert + REVOKE) before any
    params/heartbeat_core edit.

CLI:
    backtest/.venv/Scripts/python.exe backtest/autoresearch/rrw_bull_veto_study.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent      # backtest/
PROJECT_ROOT = REPO.parent                          # 42/
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(PROJECT_ROOT))

from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402
from lib.watchers.ribbon_rejection_wick_detector import RRWParams  # noqa: E402

from autoresearch.ribbon_rejection_wick_battery import load_master, load_vix  # noqa: E402

DATA = REPO / "data"
EVENTS_CACHE = REPO / "autoresearch" / "_state" / "ribbon_rejection_wick_events.jsonl"
OUT = PROJECT_ROOT / "analysis" / "recommendations" / "rrw-bull-veto-overlay.json"

WIN_START = dt.date(2025, 1, 2)
WIN_END = dt.date(2026, 7, 1)      # matches the RRW battery's own OPRA-covered window
VETO_LOOKBACK_MIN = 30             # this rule_id's own spec_origin framing, not invented here

CONFIGS = {
    "A_defaults": RRWParams(),                       # wick>=0.35 lb<=12 vol_off not_flipped
    "B_vol1.5": RRWParams(vol_mult_min=1.5),          # + J's live-anchor volx
}


def load_bear_events() -> list[dict]:
    events = []
    with EVENTS_CACHE.open(encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            if e["direction"] == "short":
                events.append(e)
    return events


def event_passes(ev: dict, cfg: RRWParams) -> bool:
    if ev["wick_frac"] < cfg.wick_frac_min:
        return False
    if ev["bars_since_break"] > cfg.break_lookback_bars:
        return False
    if cfg.vol_mult_min > 0 and ev["vol_break_ratio"] < cfg.vol_mult_min:
        return False
    if cfg.require_stack_not_flipped and ev["stack_flipped"]:
        return False
    return True


def get_bull_trades() -> list:
    spy = load_master()
    vix = load_vix()
    res = run_backtest(
        spy, vix,
        start_date=WIN_START, end_date=WIN_END,
        use_real_fills=True,
        enable_bullish=True,
        strike_offset=0,                    # ATM — live core Safe-2 tier (2026-07-11 recon)
        premium_stop_pct_bull=None,         # chart-stop-primary (L51/L55)
        block_bull_ribbon_flip=True,        # ratified 2026-06-17 — PROD_GATED
        block_bull_1100_1200=True,          # ratified 2026-06-18 — PROD_GATED
    )
    return [t for t in res.trades if "BULLISH" in t.setup]


def _stats(pnls: list[float]) -> dict:
    n = len(pnls)
    if n == 0:
        return {"n": 0, "pnl": 0.0, "wr": 0.0, "expectancy": 0.0}
    total = sum(pnls)
    return {
        "n": n,
        "pnl": round(total, 2),
        "wr": round(sum(1 for p in pnls if p > 0) / n, 3),
        "expectancy": round(total / n, 2),
    }


def veto_test(trades: list, bear_events: list, cfg: RRWParams) -> dict:
    qualifying = [e for e in bear_events if event_passes(e, cfg)]
    by_day: dict[str, list[dt.datetime]] = {}
    for e in qualifying:
        by_day.setdefault(e["date"], []).append(pd.Timestamp(e["ts"]))

    baseline_pnls = [t.dollar_pnl for t in trades]
    kept_pnls, vetoed_pnls = [], []
    vetoed_trades = []
    for t in trades:
        day = str(t.entry_time_et.date())
        entry = pd.Timestamp(t.entry_time_et)
        window_start = entry - pd.Timedelta(minutes=VETO_LOOKBACK_MIN)
        fired = any(window_start <= ts < entry for ts in by_day.get(day, []))
        if fired:
            vetoed_pnls.append(t.dollar_pnl)
            vetoed_trades.append({
                "date": day, "entry": entry.strftime("%H:%M"),
                "pnl": round(t.dollar_pnl, 2), "exit_reason": str(t.exit_reason),
            })
        else:
            kept_pnls.append(t.dollar_pnl)

    return {
        "config": {"wick_frac_min": cfg.wick_frac_min, "break_lookback_bars": cfg.break_lookback_bars,
                   "vol_mult_min": cfg.vol_mult_min, "require_stack_not_flipped": cfg.require_stack_not_flipped},
        "baseline": _stats(baseline_pnls),
        "veto_applied": _stats(kept_pnls),
        "vetoed_trades": _stats(vetoed_pnls),
        "delta_pnl_from_veto": round(sum(kept_pnls) - sum(baseline_pnls), 2),
        "n_vetoed": len(vetoed_pnls),
        "vetoed_examples": vetoed_trades[:15],
    }


def _lookup_exit_premium(t, tighten_ts: pd.Timestamp) -> float | None:
    """Real OPRA premium at the first contract bar at/after tighten_ts (next-print,
    mirrors the 'entry = next bar' convention used elsewhere in this repo).

    DST-frame fix (project_dst_frame_artifact_2026_07_02 / lib/et_frame.py): the OPRA
    option cache stores timestamp_et with a FIXED -04:00 offset year-round (mislabeled
    in EST months); load_contract_bars() parses it tz-AWARE without correcting for
    this. Our bear-event timestamps (and the SPY/Trade frame this whole study runs in)
    are et-v2 (true DST-correct ET, tz-naive) via ribbon_rejection_wick_battery.load_master().
    Re-derive the option frame the SAME et-v2 way before comparing — never join a
    naive et-v2 series against a raw/mislabeled tz-aware one."""
    sym = option_symbol(t.entry_time_et.date(), t.strike, t.side)
    opt = load_contract_bars(sym)
    if opt is None or opt.empty:
        return None
    ts_col = opt["timestamp_et"]
    if getattr(ts_col.dt, "tz", None) is not None:
        opt = opt.assign(timestamp_et=ts_col.dt.tz_convert("America/New_York").dt.tz_localize(None))
    opt = opt.sort_values("timestamp_et")
    after = opt[opt["timestamp_et"] >= tighten_ts]
    if after.empty:
        return None
    return float(after.iloc[0]["close"])


def tighten_test(trades: list, bear_events: list, cfg: RRWParams) -> dict:
    qualifying = [e for e in bear_events if event_passes(e, cfg)]
    by_day: dict[str, list[dt.datetime]] = {}
    for e in qualifying:
        by_day.setdefault(e["date"], []).append(pd.Timestamp(e["ts"]))

    baseline_pnls = [t.dollar_pnl for t in trades]
    actual_pnls, cf_pnls = [], []
    flagged = []
    opra_miss = 0
    for t in trades:
        if t.runner_exit_time_et is None:
            continue
        day = str(t.entry_time_et.date())
        entry = pd.Timestamp(t.entry_time_et)
        exit_ts = pd.Timestamp(t.runner_exit_time_et)
        during = sorted(ts for ts in by_day.get(day, []) if entry < ts < exit_ts)
        if not during:
            continue
        tighten_ts = during[0]  # first qualifying bear-wick during the hold
        exit_px = _lookup_exit_premium(t, tighten_ts)
        if exit_px is None:
            opra_miss += 1
            continue
        # Whole-position approximation (disclosed limitation — see module CAVEATS).
        cf_pnl = (exit_px - t.entry_premium) * t.qty * 100.0
        actual_pnls.append(t.dollar_pnl)
        cf_pnls.append(cf_pnl)
        flagged.append({
            "date": day, "entry": entry.strftime("%H:%M"),
            "tighten_at": tighten_ts.strftime("%H:%M"), "exit": exit_ts.strftime("%H:%M"),
            "actual_pnl": round(t.dollar_pnl, 2), "counterfactual_pnl": round(cf_pnl, 2),
            "delta": round(cf_pnl - t.dollar_pnl, 2),
        })

    return {
        "config": {"wick_frac_min": cfg.wick_frac_min, "break_lookback_bars": cfg.break_lookback_bars,
                   "vol_mult_min": cfg.vol_mult_min, "require_stack_not_flipped": cfg.require_stack_not_flipped},
        "baseline_all_bull": _stats(baseline_pnls),
        "n_flagged": len(flagged),
        "opra_miss": opra_miss,
        "actual_on_flagged": _stats(actual_pnls),
        "counterfactual_on_flagged": _stats(cf_pnls),
        "delta_pnl_from_tighten": round(sum(cf_pnls) - sum(actual_pnls), 2),
        "flagged_examples": flagged[:15],
    }


def main() -> int:
    print("=== RRW-AS-VETO-STUDY (bull path overlay) ===", flush=True)
    bear_events = load_bear_events()
    print(f"bear events (cached, direction=short): {len(bear_events)}", flush=True)

    print("running PROD_GATED bull backtest (real fills, ATM, chart-stop)...", flush=True)
    trades = get_bull_trades()
    print(f"bull trades: {len(trades)}", flush=True)

    scorecard = {
        "rule_id": "rrw-bull-veto-overlay",
        "study": "RRW-AS-VETO-STUDY",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "spec_origin": "queue.md RRW-AS-VETO-STUDY, filed 2026-07-02 after-close",
        "entry_verdict_context": "RIBBON_REJECTION_WICK is KILLED as an ENTRY (0/24 BH-FDR "
                                  "survivors, analysis/recommendations/ribbon-rejection-wick.json) "
                                  "-- this study asks a DIFFERENT question: overlay value on the "
                                  "already-live bull path.",
        "window": {"start": WIN_START.isoformat(), "end": WIN_END.isoformat()},
        "bull_config": "PROD_GATED (block_bull_ribbon_flip + block_bull_1100_1200), ATM strike, "
                       "chart-stop-primary -- what the engine actually trades today",
        "veto_lookback_minutes": VETO_LOOKBACK_MIN,
        "n_bull_trades": len(trades),
        "n_bear_events_cached": len(bear_events),
        "veto_tests": {},
        "tighten_tests": {},
    }

    for name, cfg in CONFIGS.items():
        print(f"[veto] config {name}...", flush=True)
        scorecard["veto_tests"][name] = veto_test(trades, bear_events, cfg)
        print(f"[tighten] config {name}...", flush=True)
        scorecard["tighten_tests"][name] = tighten_test(trades, bear_events, cfg)

    # Verdict: CLEARS iff at least one config's veto OR tighten test shows a genuinely
    # positive, non-trivial-n delta AND does not just remove noise (n_vetoed too small to
    # trust). Conservative bar: n>=10 affected trades AND delta > $50.
    def _config_clears(block: dict, delta_key: str, n_key: str) -> bool:
        return block[n_key] >= 10 and block[delta_key] > 50.0

    clears = []
    for name in CONFIGS:
        v = scorecard["veto_tests"][name]
        t_ = scorecard["tighten_tests"][name]
        if _config_clears(v, "delta_pnl_from_veto", "n_vetoed"):
            clears.append(f"veto/{name}")
        if _config_clears(t_, "delta_pnl_from_tighten", "n_flagged"):
            clears.append(f"tighten/{name}")

    scorecard["verdict"] = "CLEARS" if clears else "FAIL"
    scorecard["clearing_tests"] = clears
    scorecard["caveats"] = [
        "TIGHTEN counterfactual is a whole-position approximation (ignores TP1 partial "
        "fills / tp1_qty_fraction) -- directional indicator, not a production-ready dollar "
        "estimate. A real wiring proposal needs a partial-fill-aware replay.",
        "veto and tighten are tested SEPARATELY (not stacked) to keep each counterfactual "
        "legible; a trade can appear in both.",
        "No live wiring happens from this study regardless of verdict -- CLEARS still "
        "needs a separate rail-4 ratification pass (guard test + revert + REVOKE).",
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(scorecard, indent=1, default=str), encoding="utf-8")
    print(f"\nscorecard -> {OUT}", flush=True)
    print(f"\nVERDICT: {scorecard['verdict']}  clearing: {clears}", flush=True)
    for name in CONFIGS:
        v = scorecard["veto_tests"][name]
        t_ = scorecard["tighten_tests"][name]
        print(f"  [{name}] veto: n_vetoed={v['n_vetoed']:3d} delta=${v['delta_pnl_from_veto']:8.2f} "
              f"baseline_n={v['baseline']['n']} baseline_pnl=${v['baseline']['pnl']:.2f}", flush=True)
        print(f"  [{name}] tighten: n_flagged={t_['n_flagged']:3d} opra_miss={t_['opra_miss']} "
              f"delta=${t_['delta_pnl_from_tighten']:8.2f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
