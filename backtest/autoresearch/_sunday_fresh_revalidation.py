"""SUNDAY FRESH RE-VALIDATION — are the 3 real edges STILL ALIVE on the newest data?

The "are we actually profitable now" question. A1 backfilled the OPRA option-fill cache to
2026-06-18 (verified: option contract files dated 260618 exist; data-coverage.json
option_chain_realfills.last = 2026-06-18). So the window 2026-05-30..2026-06-18 is the
TRUEST-FRESH OOS we have never scored before (the old cache edge was 2026-05-29).

This is a READ-ONLY research driver. It does NOT edit any harness, watcher, params.json,
risk_gate, orchestrator, or heartbeat (Sunday money-path guard). It IMPORTS the validated
detectors + the real-OPRA sim helpers from the existing harnesses byte-for-byte and simply
re-cuts the metrics on the fresh window:

  #1 vwap_continuation  -> _edgehunt_vwap_continuation.detect_signals  (the LIVE detector)
       + WP-5 strike A/B (OTM-2 / ATM / ITM-1 / ITM-2) on the SAME fresh signal set
  #2 vwap_reclaim_failed_break -> _sub_struct_vwap_reclaim_failed_break.detect_signals
  #4 vix_regime_dayside -> _b5_vix_regime_dayside.detect_opt_signals (robust b5 cfg)
  portfolio -> combine the three fresh-window real-fills streams per account

DATA: master SPY/VIX (2025-01-01..2026-06-16) concatenated with the recent daily file
(2026-05-19..2026-06-18) so the frame covers full IS + the fresh OOS. Real OPRA fills
resolve per-contract via load_contract_bars (no window restriction) — fresh-window dates
fill because their contract files are cached (A1 backfill).

DISCLOSURE (C1/C7/OP-20): real OPRA fills only (the WR authority). Per-trade EXPECTANCY,
not WR alone. Fresh-window n is SMALL (~3 trading weeks) — reported honestly, never hidden.
edges_still_alive = the live #1 remains positive-expectancy on the fresh window.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sunday_fresh_revalidation.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _nearest_cached_strike,
    _strike_from_spot,
)
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    detect_signals as detect_vwap_continuation,
)
from autoresearch._sub_struct_vwap_reclaim_failed_break import (  # noqa: E402
    detect_signals as detect_reclaim_failed_break,
)
from autoresearch._b5_vix_regime_dayside import (  # noqa: E402
    causal_vix_median,
    vix_slope,
    detect_opt_signals as detect_vix_regime_dayside,
    _swing_stop,
    VIX_MEDIAN_BARS,
    VIX_SLOPE_BARS,
)
from autoresearch.infinite_ammo_discovery import Signal  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

DATA = REPO / "data"
OUT_JSON = ROOT / "analysis" / "recommendations" / "sunday-fresh-revalidation.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "SUNDAY-FRESH-REVALIDATION.md"
B5_SCORECARD = ROOT / "analysis" / "recommendations" / "b5-vix-regime-dayside.json"

# ── The fresh window: never-scored OOS opened by the A1 backfill ──────────────────
FRESH_START = dt.date(2026, 5, 30)
FRESH_END = dt.date(2026, 6, 18)
OLD_CACHE_EDGE = dt.date(2026, 5, 29)

PREMIUM_STOP_PCT = -0.08
MAX_STRIKE_STEPS = 4
QTY = 3

# WP-5 strike cells (sim convention: NEG=ITM, POS=OTM). live_params is the inverse label.
WP5_CELLS = [
    ("OTM-2", 2, "LIVE Safe-2 tier (the mis-strike leak)"),
    ("ATM", 0, "validated Safe-2 cell"),
    ("ITM-1", -1, "intermediate"),
    ("ITM-2", -2, "validated Bold cell"),
]


def load_merged_spy_vix() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Master (2025-01-01..2026-06-16) + recent daily file (2026-05-19..2026-06-18),
    concatenated and de-duped, so the frame covers full IS + the fresh OOS window."""
    master_spy = pd.read_csv(DATA / "spy_5m_2025-01-01_2026-06-16.csv")
    master_vix = pd.read_csv(DATA / "vix_5m_2025-01-01_2026-06-16.csv")
    recent_spy = pd.read_csv(DATA / "spy_5m_2026-05-19_2026-06-18.csv")
    recent_vix = pd.read_csv(DATA / "vix_5m_2026-05-19_2026-06-18.csv")
    spy = pd.concat([master_spy, recent_spy], ignore_index=True)
    vix = pd.concat([master_vix, recent_vix], ignore_index=True)
    return spy, vix


def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def window_metrics(rows: list[dict], start: dt.date, end: dt.date) -> dict:
    """Metrics restricted to [start, end] (inclusive). rows have date(str) + pnl(float)."""
    sub = [r for r in rows if start <= dt.date.fromisoformat(r["date"]) <= end]
    if not sub:
        return {"n": 0, "window": f"{start}..{end}"}
    pnl = np.array([r["pnl"] for r in sub], float)
    n = len(sub)
    by_day = defaultdict(float)
    for r in sub:
        by_day[r["date"]] += r["pnl"]
    days = sorted(by_day)
    daily = np.array([by_day[d] for d in days], float)
    by_side = {}
    for sd in ("C", "P"):
        s = [r["pnl"] for r in sub if r["side"] == sd]
        if s:
            by_side[sd] = {"n": len(s), "exp": round(float(np.mean(s)), 2),
                           "total": round(float(np.sum(s)), 2)}
    return {
        "window": f"{start}..{end}",
        "n": n,
        "n_days": len(days),
        "wr_pct": round(100 * float((pnl > 0).mean()), 1),
        "exp_per_trade": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "sign": "POSITIVE" if pnl.mean() > 0 else ("FLAT" if pnl.mean() == 0 else "NEGATIVE"),
        "best_day": round(float(daily.max()), 2),
        "worst_day": round(float(daily.min()), 2),
        "win_days": int((daily > 0).sum()),
        "loss_days": int((daily < 0).sum()),
        "by_side": by_side,
        "first_fill": days[0],
        "last_fill": days[-1],
    }


def simulate_set(signals, spy, ribbon, vix, *, strike_offset, setup) -> tuple[list[dict], dict]:
    """Run a signal set at one strike tier on real OPRA fills (full frame; window cut later)."""
    rows: list[dict] = []
    n_total = len(signals)
    n_filled = n_miss = n_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=QTY, setup=setup, strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=PREMIUM_STOP_PCT)
        if fill is None or fill.dollar_pnl is None:
            n_none += 1
            continue
        n_filled += 1
        rows.append({"date": str(d), "side": sg.side, "strike": int(strike),
                     "pnl": round(float(fill.dollar_pnl), 2),
                     "exit": fill.exit_reason.name if fill.exit_reason else "NONE"})
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_miss, "sim_none": n_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


def load_vix_regime_config() -> dict:
    try:
        b5 = json.loads(B5_SCORECARD.read_text(encoding="utf-8"))
        rb = b5.get("headline", {}).get("robust_clearing_cell")
        if rb and rb.get("slope_rule") is not None and rb.get("low_margin") is not None:
            return {"slope_rule": rb["slope_rule"], "low_margin": rb["low_margin"],
                    "source": "b5 robust_clearing_cell"}
    except Exception as e:  # noqa: BLE001
        print(f"[fresh] WARN b5 scorecard unreadable ({e}); default vix-regime cfg", flush=True)
    return {"slope_rule": "not_rising", "low_margin": 0.0, "source": "default"}


def main() -> int:
    print(f"[fresh] loading merged SPY+VIX (master + recent) ...", flush=True)
    spy_raw, vix_raw = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    last_bar = spy["timestamp_et"].iloc[-1].date()
    fresh_days = [dc for dc in days if FRESH_START <= dc.date <= FRESH_END]
    print(f"[fresh] frame {spy['timestamp_et'].iloc[0].date()}..{last_bar} "
          f"trading_days={len(days)} | fresh-window days={len(fresh_days)} "
          f"({FRESH_START}..{FRESH_END})", flush=True)

    # ── #1 vwap_continuation (the LIVE detector) ─────────────────────────────────
    sig_e1 = detect_vwap_continuation(days, vix, breakout_only=False, put_needs_rising_vix=False)
    e1_fresh_sig = [s for s in sig_e1 if FRESH_START <= spy.iloc[s.bar_idx]["timestamp_et"].date() <= FRESH_END]
    print(f"[fresh] #1 signals total={len(sig_e1)} fresh-window={len(e1_fresh_sig)}", flush=True)

    # WP-5 strike A/B on the SAME signal set — does the OTM-2 leak persist on fresh data?
    wp5 = []
    for label, off, role in WP5_CELLS:
        rows, cov = simulate_set(sig_e1, spy, ribbon, vix, strike_offset=off, setup=f"E1_{label}")
        fresh = window_metrics(rows, FRESH_START, FRESH_END)
        full_oos = window_metrics(rows, dt.date(2026, 1, 1), FRESH_END)
        wp5.append({"label": label, "sim_offset": off, "role": role, "coverage": cov,
                    "fresh_window": fresh, "full_oos_2026": full_oos})
        print(f"[fresh] #1 strike {label:6s}(off={off:+d}): fresh n={fresh['n']} "
              f"exp=${fresh.get('exp_per_trade')} total=${fresh.get('total_dollar')} "
              f"sign={fresh.get('sign')} | full-OOS exp=${full_oos.get('exp_per_trade')}", flush=True)

    # The two live tiers for headline #1: ATM (Safe-2 validated) + ITM-2 (Bold validated)
    e1_atm_rows, _ = simulate_set(sig_e1, spy, ribbon, vix, strike_offset=0, setup="E1_ATM")
    e1_itm2_rows, _ = simulate_set(sig_e1, spy, ribbon, vix, strike_offset=-2, setup="E1_ITM2")
    e1_otm2_rows, _ = simulate_set(sig_e1, spy, ribbon, vix, strike_offset=2, setup="E1_OTM2")

    # ── #2 vwap_reclaim_failed_break ─────────────────────────────────────────────
    sig_e2 = detect_reclaim_failed_break(days)
    e2_atm_rows, e2_cov = simulate_set(sig_e2, spy, ribbon, vix, strike_offset=0, setup="E2_ATM")
    e2_itm2_rows, _ = simulate_set(sig_e2, spy, ribbon, vix, strike_offset=-2, setup="E2_ITM2")
    e2_fresh = window_metrics(e2_atm_rows, FRESH_START, FRESH_END)
    e2_itm2_fresh = window_metrics(e2_itm2_rows, FRESH_START, FRESH_END)
    print(f"[fresh] #2 reclaim signals={len(sig_e2)} ATM fresh n={e2_fresh['n']} "
          f"exp=${e2_fresh.get('exp_per_trade')} sign={e2_fresh.get('sign')}", flush=True)

    # ── #4 vix_regime_dayside (robust b5 cfg, ATM) ───────────────────────────────
    vix_g = vix.to_numpy()
    vix_med_g = causal_vix_median(vix_g, VIX_MEDIAN_BARS)
    vix_slp_g = vix_slope(vix_g, VIX_SLOPE_BARS)
    cfg = load_vix_regime_config()
    sig_e4 = detect_vix_regime_dayside(days, spy, vix_g, vix_med_g, vix_slp_g,
                                       cfg["low_margin"], cfg["slope_rule"])
    sig_e4 = [Signal(bar_idx=s.gidx, side=s.side,
                     stop_level=round(_swing_stop(spy, s.gidx, s.side), 2),
                     note="vix_regime_dayside") for s in sig_e4]
    e4_atm_rows, e4_cov = simulate_set(sig_e4, spy, ribbon, vix, strike_offset=0, setup="E4_ATM")
    e4_fresh = window_metrics(e4_atm_rows, FRESH_START, FRESH_END)
    print(f"[fresh] #4 vix_regime cfg={cfg} signals={len(sig_e4)} ATM fresh n={e4_fresh['n']} "
          f"exp=${e4_fresh.get('exp_per_trade')} sign={e4_fresh.get('sign')}", flush=True)

    # ── 3-edge portfolio on the fresh window (per account) ───────────────────────
    def by_day(rows):
        d = defaultdict(float)
        for r in rows:
            if FRESH_START <= dt.date.fromisoformat(r["date"]) <= FRESH_END:
                d[r["date"]] += r["pnl"]
        return d

    def portfolio(*streams):
        comb = defaultdict(float)
        for st in streams:
            for d, p in by_day(st).items():
                comb[d] += p
        if not comb:
            return {"n_days": 0, "total_dollar": 0.0}
        vals = np.array([comb[d] for d in sorted(comb)], float)
        return {"n_days": len(comb), "total_dollar": round(float(vals.sum()), 2),
                "daily_mean": round(float(vals.mean()), 2),
                "win_days": int((vals > 0).sum()), "loss_days": int((vals < 0).sum()),
                "best_day": round(float(vals.max()), 2), "worst_day": round(float(vals.min()), 2),
                "sign": "POSITIVE" if vals.sum() > 0 else ("FLAT" if vals.sum() == 0 else "NEGATIVE")}

    # Safe-2 = ATM: #1 + #2 + #4 ; Bold = ITM-2: #1 + #2
    safe_pf = portfolio(e1_atm_rows, e2_atm_rows, e4_atm_rows)
    bold_pf = portfolio(e1_itm2_rows, e2_itm2_rows)
    print(f"[fresh] portfolio Safe-2(ATM 1+2+4): total=${safe_pf['total_dollar']} "
          f"days={safe_pf['n_days']} sign={safe_pf['sign']}", flush=True)
    print(f"[fresh] portfolio Bold(ITM-2 1+2): total=${bold_pf['total_dollar']} "
          f"days={bold_pf['n_days']} sign={bold_pf['sign']}", flush=True)

    # ── headline edges_still_alive logic ─────────────────────────────────────────
    e1_atm_fresh = window_metrics(e1_atm_rows, FRESH_START, FRESH_END)
    e1_itm2_fresh = window_metrics(e1_itm2_rows, FRESH_START, FRESH_END)
    e1_otm2_fresh = window_metrics(e1_otm2_rows, FRESH_START, FRESH_END)
    # live #1 alive = its validated tiers (ATM for Safe-2, ITM-2 for Bold) positive on fresh data
    e1_alive = bool((e1_atm_fresh.get("exp_per_trade") or -1) > 0
                    or (e1_itm2_fresh.get("exp_per_trade") or -1) > 0)
    edges_still_alive = e1_alive

    summary = {
        "campaign": "SUNDAY FRESH RE-VALIDATION — 3 edges on the never-scored newest OOS window",
        "run_date": dt.date.today().isoformat(),
        "fresh_window": f"{FRESH_START}..{FRESH_END}",
        "old_cache_edge": str(OLD_CACHE_EDGE),
        "a1_backfill": "BACKFILLED — option cache now ends 2026-06-18 (contract files dated 260618)",
        "frame": f"{spy['timestamp_et'].iloc[0].date()}..{last_bar} (master + recent daily concat)",
        "fresh_window_trading_days": len(fresh_days),
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "config": {"premium_stop_pct": PREMIUM_STOP_PCT, "qty": QTY, "snap_radius": MAX_STRIKE_STEPS,
                   "exits": "v15 default", "vix_regime_cfg": cfg},
        "edge1_vwap_continuation": {
            "n_signals_total": len(sig_e1), "n_signals_fresh": len(e1_fresh_sig),
            "ATM_safe2": {"fresh": e1_atm_fresh,
                          "full_oos_2026": window_metrics(e1_atm_rows, dt.date(2026, 1, 1), FRESH_END)},
            "ITM2_bold": {"fresh": e1_itm2_fresh,
                          "full_oos_2026": window_metrics(e1_itm2_rows, dt.date(2026, 1, 1), FRESH_END)},
            "OTM2_live_leak": {"fresh": e1_otm2_fresh,
                               "full_oos_2026": window_metrics(e1_otm2_rows, dt.date(2026, 1, 1), FRESH_END)},
            "wp5_strike_ab": wp5,
            "alive_on_fresh": e1_alive,
        },
        "edge2_vwap_reclaim_failed_break": {
            "n_signals": len(sig_e2), "coverage_atm": e2_cov,
            "ATM_safe2_fresh": e2_fresh, "ITM2_bold_fresh": e2_itm2_fresh,
            "ATM_full_oos_2026": window_metrics(e2_atm_rows, dt.date(2026, 1, 1), FRESH_END),
        },
        "edge4_vix_regime_dayside": {
            "n_signals": len(sig_e4), "coverage_atm": e4_cov, "cfg": cfg,
            "ATM_safe2_fresh": e4_fresh,
            "ATM_full_oos_2026": window_metrics(e4_atm_rows, dt.date(2026, 1, 1), FRESH_END),
        },
        "portfolio_fresh": {"Safe2_ATM_1+2+4": safe_pf, "Bold_ITM2_1+2": bold_pf},
        "edges_still_alive": edges_still_alive,
        "DISCLOSURE": {
            "small_n": (f"the fresh window is ~{len(fresh_days)} trading days — n per edge is SMALL; "
                        "treat fresh-window expectancy as a directional sanity check, not a "
                        "standing-bar ratification (the 11-gate bar needs full-history n)"),
            "per_trade": "per-trade EXPECTANCY reported, not WR alone (OP-14)",
            "real_fills": "real OPRA fills only — the WR authority (C1); SPY-direction != option edge (C3/L58)",
            "no_new_ship": "RESEARCH ONLY; no live edit on a Sunday (money-path guard)",
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_md(summary)
    print(f"\n[fresh] wrote {OUT_JSON}\n[fresh] wrote {OUT_MD}", flush=True)

    print("\n=== SUNDAY FRESH RE-VALIDATION VERDICT ===")
    print(f"fresh window {FRESH_START}..{FRESH_END} ({len(fresh_days)} trading days)")
    print(f"#1 vwap_continuation ATM:  n={e1_atm_fresh['n']} exp=${e1_atm_fresh.get('exp_per_trade')} "
          f"total=${e1_atm_fresh.get('total_dollar')} {e1_atm_fresh.get('sign')}")
    print(f"#1 vwap_continuation ITM2: n={e1_itm2_fresh['n']} exp=${e1_itm2_fresh.get('exp_per_trade')} "
          f"total=${e1_itm2_fresh.get('total_dollar')} {e1_itm2_fresh.get('sign')}")
    print(f"#1 vwap_continuation OTM2(live leak): n={e1_otm2_fresh['n']} "
          f"exp=${e1_otm2_fresh.get('exp_per_trade')} {e1_otm2_fresh.get('sign')}")
    print(f"#2 reclaim ATM: n={e2_fresh['n']} exp=${e2_fresh.get('exp_per_trade')} {e2_fresh.get('sign')}")
    print(f"#4 vix_regime ATM: n={e4_fresh['n']} exp=${e4_fresh.get('exp_per_trade')} {e4_fresh.get('sign')}")
    print(f"portfolio Safe-2: ${safe_pf['total_dollar']} ({safe_pf['sign']})  "
          f"Bold: ${bold_pf['total_dollar']} ({bold_pf['sign']})")
    print(f"EDGES STILL ALIVE (live #1 positive on fresh): {edges_still_alive}")
    return 0


def write_md(s: dict) -> None:
    L = []
    L.append("# Sunday Fresh Re-Validation — are the 3 edges STILL ALIVE on the newest data?\n")
    L.append(f"- Run: {s['run_date']}  |  Fresh window: **{s['fresh_window']}** "
             f"({s['fresh_window_trading_days']} trading days)")
    L.append(f"- A1 backfill: {s['a1_backfill']}")
    L.append(f"- Frame: {s['frame']}  |  Fills: {s['fills_authority']}")
    L.append(f"- Config: {s['config']['premium_stop_pct']} stop, qty {s['config']['qty']}, "
             f"v15 exits; vix-regime cfg = {s['config']['vix_regime_cfg']}")
    L.append(f"\n## VERDICT: edges_still_alive = **{s['edges_still_alive']}**\n")
    L.append("_The fresh window is ~3 trading weeks — n is small per edge. This is a directional "
             "sanity check on the never-before-scored OOS, NOT a standing-bar ratification._\n")

    def row(m):
        if not m or not m.get("n"):
            return "n=0 (no fills in window)"
        return (f"n={m['n']} ({m['n_days']}d) | exp **${m['exp_per_trade']}/tr** | "
                f"total ${m['total_dollar']} | WR {m['wr_pct']}% | {m['sign']} | "
                f"days +{m['win_days']}/-{m['loss_days']}")

    L.append("## #1 vwap_continuation (the LIVE edge — its detector is byte-for-byte the live watcher)\n")
    e1 = s["edge1_vwap_continuation"]
    L.append(f"- signals: total {e1['n_signals_total']}, fresh-window {e1['n_signals_fresh']}")
    L.append(f"- **ATM (Safe-2 validated)** fresh: {row(e1['ATM_safe2']['fresh'])}")
    L.append(f"- **ITM-2 (Bold validated)** fresh: {row(e1['ITM2_bold']['fresh'])}")
    L.append(f"- OTM-2 (the LIVE mis-strike) fresh: {row(e1['OTM2_live_leak']['fresh'])}")
    L.append(f"- alive on fresh: **{e1['alive_on_fresh']}**\n")
    L.append("### WP-5 strike A/B on the fresh signal set (does the OTM-2 leak persist?)\n")
    L.append("| strike | role | fresh n | fresh exp/tr | fresh total | sign | full-OOS-2026 exp/tr |")
    L.append("|---|---|---|---|---|---|---|")
    for c in e1["wp5_strike_ab"]:
        f = c["fresh_window"]
        fo = c["full_oos_2026"]
        L.append(f"| {c['label']} | {c['role']} | {f.get('n', 0)} | "
                 f"${f.get('exp_per_trade', '-')} | ${f.get('total_dollar', '-')} | "
                 f"{f.get('sign', '-')} | ${fo.get('exp_per_trade', '-')} |")
    L.append("")

    L.append("## #2 vwap_reclaim_failed_break (dormant)\n")
    e2 = s["edge2_vwap_reclaim_failed_break"]
    L.append(f"- signals: {e2['n_signals']}")
    L.append(f"- ATM fresh: {row(e2['ATM_safe2_fresh'])}")
    L.append(f"- ITM-2 fresh: {row(e2['ITM2_bold_fresh'])}")
    L.append(f"- ATM full-OOS-2026: {row(e2['ATM_full_oos_2026'])}\n")

    L.append("## #4 vix_regime_dayside (dormant, ATM)\n")
    e4 = s["edge4_vix_regime_dayside"]
    L.append(f"- cfg: {e4['cfg']}  |  signals: {e4['n_signals']}")
    L.append(f"- ATM fresh: {row(e4['ATM_safe2_fresh'])}")
    L.append(f"- ATM full-OOS-2026: {row(e4['ATM_full_oos_2026'])}\n")

    L.append("## 3-edge portfolio (fresh window, real fills, per account)\n")
    pf = s["portfolio_fresh"]
    L.append("| book | days | total$ | daily mean$ | day +/- | best/worst day | sign |")
    L.append("|---|---|---|---|---|---|---|")
    for lbl, p in pf.items():
        if not p.get("n_days"):
            L.append(f"| {lbl} | 0 | - | - | - | - | - |")
            continue
        L.append(f"| {lbl} | {p['n_days']} | ${p['total_dollar']} | ${p['daily_mean']} | "
                 f"+{p['win_days']}/-{p['loss_days']} | ${p['best_day']}/${p['worst_day']} | {p['sign']} |")
    L.append("")
    L.append("## How to read this\n")
    L.append("- **edges_still_alive = live #1 positive-expectancy on the never-scored fresh OOS.** "
             "It is the 'are we actually profitable now' answer.")
    L.append("- Small-n caveat: ~3 weeks. A single big day swings the per-trade number. The full-OOS-2026 "
             "column is the larger-n companion read.")
    L.append("- Real OPRA fills (C1). Per-trade EXPECTANCY, not WR (OP-14). SPY-direction != option edge (C3/L58).")
    L.append("- RESEARCH ONLY — no live edit on a Sunday (money-path guard).")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
