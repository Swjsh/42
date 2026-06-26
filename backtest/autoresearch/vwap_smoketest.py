"""B1 LIVE-FIRE SMOKE TEST — vwap_continuation end-to-end wiring proof.

The one LIVE edge (params.json#j_vwap_cont_enabled=true) has produced ZERO tracked
fills (journal/trades.csv has no VWAP_CONTINUATION row). This script PROVES whether the
watcher -> heartbeat -> would-be-order path actually fires on a replayed historical
signal day, or whether there is a silent wiring break.

This is a REPLAY/TRACE. It places NO orders. It asserts:
  (1) the RESEARCH detector (autoresearch._edgehunt_vwap_continuation.detect_signals,
      the byte-for-byte port the LIVE watcher mirrors) fires from cached 5m bars on
      signal dates that fall INSIDE the OPRA option cache span (<= 2026-05-29);
  (2) the LIVE watcher (lib.watchers.vwap_continuation_watcher.detect_vwap_continuation_setup),
      fed a streaming BarContext rebuilt bar-by-bar from those same cached bars, emits a
      VWAP_CONTINUATION WatcherSignal with the SAME side + same trigger bar as the
      research detector (parity = no silent drift);
  (3) the watcher is REGISTERED in the live fleet (lib.watchers.runner.WATCHERS) so the
      live loop actually calls it;
  (4) the heartbeat decision path WOULD emit ENTER VWAP_CONTINUATION with the correct
      side (call on up-trend / put on down-trend) and the per-account strike the
      heartbeat block (heartbeat.md ### VWAP_CONTINUATION) computes from the v15 strike
      tier for the LIVE-enabled account (Safe-2), plus a real-OPRA fill sanity check.

DATA-COVERAGE HARD WINDOW: OPRA real-fills cache ends 2026-05-29. Every date this script
touches for a real fill is asserted <= 2026-05-29, and the last fill date is printed.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/vwap_smoketest.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy, _align_vix, detect_signals,
)
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts, _nearest_cached_strike, _strike_from_spot,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.filters import BarContext  # noqa: E402
from lib.watchers import runner as wrunner  # noqa: E402
from lib.watchers.vwap_continuation_watcher import (  # noqa: E402
    detect_vwap_continuation_setup, _reset_day,
)

OUT_MD = ROOT / "analysis" / "recommendations" / "B1-VWAP-SMOKETEST.md"
STATUS = ROOT / "automation" / "overnight" / "STATUS.md"

# Hard cap: real-fills OPRA cache last day (data-coverage.json).
CACHE_LAST = dt.date(2026, 5, 29)
PARAMS = ROOT / "automation" / "state" / "params.json"
AGG_PARAMS = ROOT / "automation" / "state" / "aggressive" / "params.json"
N_SMOKE_DAYS = 3   # number of signal dates inside the cache window to fire end-to-end
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)


# ─────────────────────────────────────────────────────────────────────────────
def _safe_tier_strike_offset(equity: float, params: dict) -> tuple[int, str]:
    """The strike_offset the LIVE heartbeat picks for the given account equity from
    v15_strike_offset_per_tier. NOTE the heartbeat's own sign convention here:
    NEGATIVE = OTM, POSITIVE = ITM (opposite of simulator_real). Returns (offset, label)."""
    for tier in params.get("v15_strike_offset_per_tier", []):
        if tier["equity_min"] <= equity < tier["equity_max"]:
            return int(tier["strike_offset"]), tier.get("label", "?")
    return 0, "ATM(fallback)"


def _build_ctx(prior_bars: pd.DataFrame, vix_now: float, vix_prior: float) -> BarContext:
    cur = prior_bars.iloc[-1]
    return BarContext(
        bar_idx=len(prior_bars) - 1,
        timestamp_et=cur["timestamp_et"],
        bar=cur,
        prior_bars=prior_bars,
        ribbon_now=None,
        ribbon_history=[],
        vix_now=vix_now,
        vix_prior=vix_prior,
        vol_baseline_20=float(prior_bars["volume"].tail(20).mean() or 1000.0),
        range_baseline_20=0.5,
        levels_active=[],
        multi_day_levels=[],
        htf_15m_stack=None,
        level_states=[],
        fhh_level=None,
        vix_5d_ma=vix_now,
        vix_20d_ma=vix_now,
    )


def _replay_live_watcher(day_df: pd.DataFrame, vix_day: pd.Series,
                         put_vix_gate: bool) -> Optional[dict]:
    """Stream today's RTH bars one-by-one through the LIVE watcher exactly as the live
    loop would (chronological, prior_bars = today's bars[0..i]). Return the first
    WatcherSignal as a dict, or None. Resets per-day module state first."""
    rth = day_df[(day_df["t"] >= RTH_OPEN) & (day_df["t"] < RTH_CLOSE)].reset_index(drop=True)
    _reset_day("smoketest-reset")  # clear any leaked module state from a prior day
    for i in range(len(rth)):
        prior = rth.iloc[: i + 1].copy()
        vix_now = float(vix_day.iloc[i]) if i < len(vix_day) else 0.0
        vix_prior = float(vix_day.iloc[i - 1]) if i > 0 else vix_now
        ctx = _build_ctx(prior, vix_now, vix_prior)
        sig = detect_vwap_continuation_setup(ctx, put_needs_rising_vix=put_vix_gate)
        if sig is not None:
            return {
                "fire_time_et": ctx.timestamp_et.strftime("%H:%M"),
                "rth_bar_idx": i,
                "setup_name": sig.setup_name,
                "direction": sig.direction,
                "side": "C" if sig.direction == "long" else "P",
                "trigger": sig.metadata.get("trigger"),
                "entry_price": round(sig.entry_price, 2),
                "stop_price": round(sig.stop_price, 2),
                "confidence": sig.confidence,
                "watcher_name": sig.watcher_name,
                "promotion_status": sig.metadata.get("promotion_status"),
                "meta_strike_offset": sig.metadata.get("strike_offset"),
                "triggers_fired": sig.triggers_fired,
            }
    return None


def main() -> int:
    print("[b1] loading SPY+VIX (window <= cache-last) via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), CACHE_LAST)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    print(f"[b1] SPY bars={len(spy)} trading_days={len(days)} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    # ── Params / live-flag introspection ─────────────────────────────────────
    params = json.loads(PARAMS.read_text(encoding="utf-8"))
    agg_params = json.loads(AGG_PARAMS.read_text(encoding="utf-8"))
    cont_enabled_safe = params.get("j_vwap_cont_enabled", False)
    cont_side_safe = params.get("j_vwap_cont_side", "both")
    cont_putgate_safe = params.get("j_vwap_cont_put_vix_gate", False)
    cont_enabled_bold = agg_params.get("j_vwap_cont_enabled", False)  # absent -> False
    safe_equity = 2000.0   # Gamma-Safe-2 ($2K), CLAUDE.md account context
    safe_off, safe_label = _safe_tier_strike_offset(safe_equity, params)

    # ── (3) registry check — is the watcher actually in the LIVE fleet? ───────
    registered = "vwap_continuation_watcher" in wrunner.registered_watcher_names()

    # ── (1) RESEARCH detector — signals on cached bars (the live-watcher port) ─
    signals = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sig_by_date: dict[dt.date, dict] = {}
    for s in signals:
        d = spy.iloc[s.bar_idx]["timestamp_et"].date()
        if d <= CACHE_LAST and d not in sig_by_date:
            sig_by_date[d] = {"side": s.side, "bar_idx": int(s.bar_idx),
                              "stop_level": float(s.stop_level), "note": s.note,
                              "fire_time_et": spy.iloc[s.bar_idx]["timestamp_et"].strftime("%H:%M")}
    in_cache_dates = sorted(sig_by_date.keys())
    print(f"[b1] research detector: {len(signals)} signals; "
          f"{len(in_cache_dates)} on distinct dates <= {CACHE_LAST}", flush=True)

    # pick the LAST N in-cache signal dates (most recent = closest to live)
    smoke_dates = in_cache_dates[-N_SMOKE_DAYS:]
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    cases = []
    last_fill_date = None
    for d in smoke_dates:
        rsig = sig_by_date[d]
        day_df = spy[spy["date"] == d].reset_index(drop=True)
        # align the per-day VIX slice to the RTH bar count the watcher will see
        rth_mask = (day_df["t"] >= RTH_OPEN) & (day_df["t"] < RTH_CLOSE)
        rth_idx = day_df[rth_mask].index
        vix_day = vix.iloc[[spy.index[spy["date"] == d][k] for k in rth_idx]].reset_index(drop=True) \
            if False else pd.Series([float(vix.iloc[i]) for i in spy.index[(spy["date"] == d) & (spy["t"] >= RTH_OPEN) & (spy["t"] < RTH_CLOSE)]])

        # (2) LIVE watcher streaming replay
        live = _replay_live_watcher(day_df, vix_day, put_vix_gate=bool(cont_putgate_safe))

        # parity vs research detector
        parity_side = live is not None and live["side"] == rsig["side"]
        parity_time = live is not None and live["fire_time_et"] == rsig["fire_time_et"]

        # (4) heartbeat decision trace — strike the LIVE (Safe-2) account would pick.
        # heartbeat sign: NEGATIVE=OTM => to get the SIM offset (NEGATIVE=ITM) we negate.
        sim_strike_offset = -safe_off
        bar = spy.iloc[rsig["bar_idx"]]
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - sim_strike_offset if rsig["side"] == "P" else atm + sim_strike_offset
        strike = _nearest_cached_strike(d, target, rsig["side"], 4)
        fill = None
        if strike is not None:
            entry_vix = float(vix.iloc[rsig["bar_idx"]]) if rsig["bar_idx"] < len(vix) else 0.0
            f = simulate_trade_real(
                entry_bar_idx=rsig["bar_idx"], entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
                rejection_level=rsig["stop_level"], triggers_fired=[rsig["note"]],
                side=rsig["side"], qty=3, setup="VWAP_CONTINUATION_SMOKE",
                strike_override=strike, entry_vix=entry_vix,
                premium_stop_pct=-0.99,  # chart-stop-only (live VWAP_CONTINUATION exit)
                tp1_premium_pct=0.30, runner_target_premium_pct=2.5,
            )
            if f is not None and f.dollar_pnl is not None:
                last_fill_date = d
                fill = {
                    "strike": int(strike), "atm": int(atm),
                    "entry_premium": round(float(f.entry_premium), 4),
                    "pnl": round(float(f.dollar_pnl), 2),
                    "exit_reason": f.exit_reason.name if f.exit_reason else "NONE",
                }

        case = {
            "date": str(d),
            "research_detector": rsig,
            "live_watcher": live,
            "live_fired": live is not None,
            "parity_side": parity_side,
            "parity_fire_time": parity_time,
            "heartbeat_trace": {
                "live_enabled_account": "Gamma-Safe-2" if cont_enabled_safe else "NONE",
                "safe_equity": safe_equity,
                "heartbeat_strike_offset": safe_off,
                "heartbeat_strike_label": safe_label,
                "sim_strike_offset_convention": sim_strike_offset,
                "would_enter_side": ("CALLS" if rsig["side"] == "C" else "PUTS"),
                "side_gated_allowed": (
                    (rsig["side"] == "C" and cont_side_safe in ("both", "call")) or
                    (rsig["side"] == "P" and cont_side_safe in ("both", "put"))
                ),
            },
            "real_fill": fill,
        }
        cases.append(case)
        ls = (f"LIVE {live['direction']}/{live['side']} @ {live['fire_time_et']} trig={live['trigger']}"
              if live else "LIVE no-fire")
        fs = f"fill pnl=${fill['pnl']} ({fill['exit_reason']})" if fill else "fill NONE"
        print(f"  {d}: research {rsig['side']} @ {rsig['fire_time_et']} | {ls} | "
              f"parity_side={parity_side} parity_time={parity_time} | {fs}", flush=True)

    # ── VERDICT ───────────────────────────────────────────────────────────────
    n_live = sum(1 for c in cases if c["live_fired"])
    n_parity = sum(1 for c in cases if c["parity_side"] and c["parity_fire_time"])
    n_fill = sum(1 for c in cases if c["real_fill"] is not None)

    wiring_ok = bool(
        cont_enabled_safe and registered and n_live == len(cases)
        and n_parity == len(cases)
    )
    if wiring_ok and n_fill == len(cases):
        verdict = "LIVE_EDGE_FIRES_OK"
    elif not wiring_ok:
        verdict = "LIVE_EDGE_BROKEN"
    else:
        verdict = "INCONCLUSIVE"

    summary = {
        "verdict": verdict,
        "ran": True,
        "wiring_ok": wiring_ok,
        "registered_in_live_fleet": registered,
        "j_vwap_cont_enabled_safe": cont_enabled_safe,
        "j_vwap_cont_enabled_bold": cont_enabled_bold,
        "j_vwap_cont_side_safe": cont_side_safe,
        "j_vwap_cont_put_vix_gate_safe": cont_putgate_safe,
        "safe2_heartbeat_strike": f"{safe_label} (offset {safe_off})",
        "n_research_signals_total": len(signals),
        "n_signal_dates_in_cache": len(in_cache_dates),
        "smoke_dates": [str(x) for x in smoke_dates],
        "n_cases": len(cases),
        "n_live_fired": n_live,
        "n_parity": n_parity,
        "n_real_fill": n_fill,
        "last_fill_date": str(last_fill_date) if last_fill_date else None,
        "cache_last": str(CACHE_LAST),
        "cases": cases,
    }

    _write_md(summary)
    print(f"\n[b1] wrote {OUT_MD}", flush=True)
    print(f"\n=== B1 VWAP_CONTINUATION SMOKE-TEST VERDICT: {verdict} ===")
    print(f"enabled(Safe)={cont_enabled_safe} enabled(Bold)={cont_enabled_bold} "
          f"registered={registered} | live_fired={n_live}/{len(cases)} "
          f"parity={n_parity}/{len(cases)} fills={n_fill}/{len(cases)} "
          f"last_fill={last_fill_date}")
    return 0


def _write_md(s: dict) -> None:
    L = []
    L.append("# B1 — VWAP_CONTINUATION LIVE-FIRE SMOKE TEST")
    L.append("")
    L.append(f"**Verdict: `{s['verdict']}`**  (run {dt.datetime.now().isoformat(timespec='seconds')})")
    L.append("")
    L.append("Proves whether the one LIVE edge (`j_vwap_cont_enabled=true`) fires "
             "watcher -> heartbeat -> would-be-order end-to-end, or is silently broken. "
             "REPLAY/TRACE only — NO orders placed.")
    L.append("")
    L.append("## Wiring facts")
    L.append(f"- `j_vwap_cont_enabled` **Safe-2** = `{s['j_vwap_cont_enabled_safe']}` (LIVE), "
             f"**Bold** = `{s['j_vwap_cont_enabled_bold']}` (absent key -> inert on Bold)")
    L.append(f"- `j_vwap_cont_side` (Safe) = `{s['j_vwap_cont_side_safe']}`; "
             f"`j_vwap_cont_put_vix_gate` (Safe) = `{s['j_vwap_cont_put_vix_gate_safe']}`")
    L.append(f"- watcher registered in live fleet (`runner.WATCHERS`): "
             f"**{s['registered_in_live_fleet']}**")
    L.append(f"- Safe-2 ($2K) heartbeat strike tier: **{s['safe2_heartbeat_strike']}** "
             f"(heartbeat sign convention: NEGATIVE=OTM)")
    L.append("")
    L.append("## Coverage (hard-windowed to OPRA cache)")
    L.append(f"- OPRA cache last day: `{s['cache_last']}`; last real fill in this run: "
             f"`{s['last_fill_date']}`")
    L.append(f"- research signals total (2025-01..{s['cache_last']}): {s['n_research_signals_total']}; "
             f"distinct signal dates in cache: {s['n_signal_dates_in_cache']}")
    L.append(f"- smoke dates (most-recent in-cache): {', '.join(s['smoke_dates'])}")
    L.append("")
    L.append("## Per-date end-to-end trace")
    L.append("")
    L.append("| date | research side@time | live watcher | parity (side/time) | "
             "would-enter | strike | real fill |")
    L.append("|---|---|---|---|---|---|---|")
    for c in s["cases"]:
        r = c["research_detector"]
        lv = c["live_watcher"]
        ht = c["heartbeat_trace"]
        f = c["real_fill"]
        lvs = (f"{lv['direction']}/{lv['side']} @{lv['fire_time_et']} {lv['trigger']}"
               if lv else "NO FIRE")
        par = f"{c['parity_side']}/{c['parity_fire_time']}"
        ent = (f"{ht['would_enter_side']} (allowed={ht['side_gated_allowed']})")
        strk = (f"{f['strike']} (atm {f['atm']})" if f else f"off {ht['heartbeat_strike_offset']}")
        fs = (f"${f['pnl']} {f['exit_reason']} @prem {f['entry_premium']}" if f else "NONE")
        L.append(f"| {c['date']} | {r['side']} @{r['fire_time_et']} | {lvs} | {par} | "
                 f"{ent} | {strk} | {fs} |")
    L.append("")
    L.append("## Interpretation")
    L.append(f"- live fired: {s['n_live_fired']}/{s['n_cases']} | "
             f"detector parity: {s['n_parity']}/{s['n_cases']} | "
             f"real fills: {s['n_real_fill']}/{s['n_cases']}")
    if s["verdict"] == "LIVE_EDGE_FIRES_OK":
        L.append("- **WIRED CORRECTLY.** The watcher is registered and fires; the LIVE "
                 "(Safe-2, enabled=true) heartbeat block would ENTER with the correct side, "
                 "the per-tier strike, and a real OPRA fill. The zero tracked fills are "
                 "explained by **no qualifying signal day since the flag went live (< 2 "
                 "trading days ago)** + Bold inert (no flag), NOT a wiring break.")
    elif s["verdict"] == "LIVE_EDGE_BROKEN":
        L.append("- **WIRING BREAK.** See which assertion failed (enabled flag / registry / "
                 "live-fire / parity). The zero tracked fills are a real bug.")
    else:
        L.append("- **INCONCLUSIVE.** Wiring is sound but a real-fill leg is missing on a "
                 "smoke date (cache snap / sim None). Inspect the per-date table.")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
