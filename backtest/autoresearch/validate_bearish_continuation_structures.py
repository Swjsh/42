"""Bearish-CONTINUATION *structure* validation — do trendline/momentum/vwap entries fire WITH J's edge?

Strategic sequel to validate_bearish_continuation_family.py (research #26). That run tested the
LEVEL-REJECTION family (BEARISH_REJECTION_MORNING, LEVEL_BREAK_FIRST_STRIKE, HEAD_AND_SHOULDERS_BEAR,
BEARISH_REVERSAL_AT_LEVEL, STAIRSTEP) and concluded:
    BEARISH_REJECTION_RIDE_THE_RIBBON (codified BEARISH_REJECTION_MORNING) is the ONLY entry that
    captures J's anchor days on REAL fills (+$134 ATM / +$197 ITM2); every other level-rejection
    variant is anti-edge or has zero anchor coverage; the broad bearish population collapses to
    NEGATIVE real-fills expectancy under chart-stop-only.

THE OPEN QUESTION (this script): are there OTHER entry STRUCTURES — genuinely different from
level-rejection — that fire WITH J's bearish-continuation edge? Three EXISTING-but-untested-for-
edge-alignment detectors, all forced BEAR side / puts:

  1. TBR_HIGH_VOL  (tbr_high_vol_watcher.detect_tbr_high_vol_setup)
       A TRENDLINE-break-retest on high volume (>=1.5x 20-bar). Structurally distinct from level
       rejection — this is the playbook's TRENDLINE_BREAK_VOLUME candidate. SHOTGUN single-exit
       doctrine in production (no runner), but graded here with the SAME TP1+runner real-fills model
       as every other family member so edge_capture is apples-to-apples.
       LOOK-AHEAD NOTE: in production it reads automation/state/key-levels.json (TODAY's levels) via
       shotgun_scalper_watcher._load_levels. We MONKEYPATCH that to historically-detected ★★+ levels
       per bar-date (same fix validate_breakout_family applies to STAIRSTEP). The detector also
       auto-derives intraday levels from the bar window (auto_derive_intraday_levels=True), so the
       trendline path is exercised regardless.

  2. MOMENTUM_ACCELERATION_HIGHVOL  (momentum_acceleration_highvol_watcher, BEAR side only)
       Momentum-CONTINUATION structure: a fast expanding-volume bar, ribbon ALIGNED, VIX>=20. The
       watcher fires BOTH directions; this harness keeps only direction=="short" (bearish
       continuation). The watcher's own docstring already flags the bear side as the drag at VIX>=25
       (N=7 WR=42.9% -$435 on a curated scan); this confirms/denies that on the anchor-aligned full
       replay with real fills.

  3. VWAP_REJECTION_PRIME  (vwap_watcher.detect_vwap_setup, BEAR side only)
       Rejection of session VWAP from below on a down day = continuation. Distinct from a named-level
       rejection (the reference is the dynamic session VWAP, not a horizontal key level). Bear side
       only (direction=="short").

METHOD (reuses the family harness wholesale — lean, per task):
  * vbf  = validate_breakout_family : _load_data / _grade / _stats / _per_quarter / _anchor_capture /
           ANCHORS / the crypto.lib.chart_patterns bootstrap / simulate_trade_real.
  * vbf2 = validate_bearish_continuation_family : the PUTS-ATM+ITM2 real-fills + anchor_real_fills
           edge_capture structure + verdict shape (anchor-inclusive cap fix reused verbatim).
  * Same per-bar BarContext pipeline with HISTORICALLY-REBUILT ★★ levels (no look-ahead), same
    ribbon/vix alignment, same EOD=15:50.
  * Real-fills: side="P" for all (bearish), qty=3, chart-stop only (premium_stop_pct=-0.99 per
    L51/L55), ATM (offset 0) + ITM2 (offset -2). Cap = first 120 signals/stream, ANCHOR-INCLUSIVE.
  * DSR/PSR advisory gate on per-trade $ P&L (constant qty=3 notional -> comparable), n_trials = 3
    (the three structures searched) — Bailey & Lopez de Prado deflation, matches sweep_timecond_exit.

THE GATE (honest — do NOT loosen to manufacture a win):
  PROMOTE-CANDIDATE iff   real-fills ATM exp > 0
                     AND  REAL-FILLS anchor edge_capture POSITIVE (captures J's 4/29-5/01-5/04
                          winners; does NOT profit on his 5/05-5/07 loss days)
                     AND  DSR not FAIL.
  If none clear (the prior family research says this is the likely outcome), the deliverable is the
  honest ranking + the conclusive verdict: which structure is least-bad / closest, and whether ANY
  bearish-continuation structure beyond BEARISH_REJECTION is worth building on.

OP-20 disclosure: SPY-space grade is a proxy (SPY move x 100), NOT real option P&L — real_fills is
the authority (C1/C3). Levels are historically-rebuilt ★★ proxies (active+multi_day from
_detect_from_history), NOT production ★★★ named levels; a true ★★★ historical validation is
impossible (no key-levels archive over the window). TBR's production key-levels.json read is a
look-ahead trap, neutralized here via the historical-level monkeypatch. The break/ribbon/structure
logic uses clean ctx.prior_bars (no look-ahead).

Usage:
  python -m autoresearch.validate_bearish_continuation_structures --realfills \
      --out ../analysis/recommendations/bearish-continuation-structures.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

# Reuse the breakout-family harness (bootstrap, data, ctx, grading, anchor scorer, simulate).
from autoresearch import validate_breakout_family as vbf  # noqa: E402
# Reuse the bearish-continuation-family real-fills/anchor-edge + dedup helpers.
from autoresearch import validate_bearish_continuation_family as vbf2  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent

from lib.filters import vol_baseline_20bar, range_baseline_20bar, BarContext  # noqa: E402
from lib.ribbon import compute_ribbon, RibbonState  # noqa: E402
from lib.levels import _detect_from_history  # noqa: E402
from lib.orchestrator import (  # noqa: E402
    _align_vix_to_spy,
    _precompute_htf_15m_stacks,
    _update_level_states,
)
from lib.validation.gate import evaluate_candidate  # noqa: E402

# ── The three structure detectors + their modules (for monkeypatch / state reset) ──
from lib.watchers import tbr_high_vol_watcher as _tbr  # noqa: E402
from lib.watchers import shotgun_scalper_watcher as _sgw  # noqa: E402  (TBR loads levels via this)
from lib.watchers import momentum_acceleration_highvol_watcher as _mahv  # noqa: E402
from lib.watchers import vwap_watcher as _vw  # noqa: E402

ANCHORS = vbf.ANCHORS
EOD = vbf.EOD

# Stream names (ranking-presentation order). All are BEAR/puts continuation structures.
_TBR = "TBR_HIGH_VOL_BEAR"
_MOM = "MOMENTUM_ACCELERATION_HIGHVOL_BEAR"
_VWAP = "VWAP_REJECTION_PRIME_BEAR"
_STREAMS = [_TBR, _MOM, _VWAP]

# Every structure is taken as PUTS at ATM (anchor strike class) and ITM2 (Bold strike class).
_OFFSETS = (("ATM", 0), ("ITM2", -2))

# n_trials for DSR deflation = number of structures searched in this family.
N_TRIALS = len(_STREAMS)

_VARIANT_NOTES = {
    _TBR: ("TRENDLINE-break-retest, high-vol (>=1.5x). The playbook TRENDLINE_BREAK_VOLUME candidate "
           "— structurally distinct from level rejection. Prior TBR work (tbr_hv_*.json) is SHOTGUN-"
           "grader walk-forward only; this is the FIRST anchor-aligned real-fills edge_capture read. "
           "Bear side only. Look-ahead key-levels read monkeypatched to historical ★★+ levels."),
    _MOM: ("Momentum-CONTINUATION (fast expanding-vol bar + ALIGNED ribbon + VIX>=20), BEAR side only. "
           "Watcher docstring flags bear side as the drag (curated scan VIX>=25 N=7 WR=42.9% -$435). "
           "This confirms/denies on the anchor-aligned full replay with real fills."),
    _VWAP: ("Session-VWAP rejection from below on a down day = continuation. Reference is the dynamic "
            "VWAP, not a horizontal key level — distinct structure. BEAR side only. Spec defaults "
            "(strategy/vwap_rejection_prime.md), NOT ratified."),
}


def _reset_state() -> None:
    """Reset module-level cooldown/cache state so a fresh replay is deterministic."""
    _mahv._last_signal_time = None
    # tbr_high_vol / shotgun_scalper_detector are stateless per-call (no module cooldown to clear).
    # vwap_watcher is stateless per-call.


# ── TBR look-ahead fix: feed historically-detected ★★+ levels per day (mirrors STAIRSTEP fix) ──
_tbr_levels_by_date: dict[str, list[dict]] = {}


def _patched_tbr_load_levels(path=None):
    """Monkeypatch replacement for shotgun_scalper_watcher._load_levels.

    tbr_high_vol_watcher calls _load_levels() (imported from shotgun_scalper_watcher) with no args.
    We return the historically-detected ★★+ levels for the CURRENT bar-date (set each bar in run()),
    in the dict shape the SHOTGUN detector expects ({'price','label','tier','type','stars'}). No
    look-ahead: levels are from _detect_from_history as-of the bar-date.
    """
    return list(_tbr_levels_by_date.get(_CUR_DATE[0], []))


# Mutable holder for the current bar-date (so the no-arg monkeypatch can see it).
_CUR_DATE: list[str | None] = [None]


def run(start: dt.date, end: dt.date, do_realfills: bool) -> dict:
    """Replay the 3 bearish-continuation STRUCTURES over [start, end]; grade + anchor-score."""
    spy_full, vix_full = vbf._load_data(start, end)
    spy_full["timestamp_et"] = vbf.pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
                   (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    ribbon_df = compute_ribbon(rth["close"])
    vix_aligned = _align_vix_to_spy(rth, vix_full)
    htf_stacks = _precompute_htf_15m_stacks(rth)

    # Patch TBR's level loader to historical levels (look-ahead fix).
    _sgw._load_levels = _patched_tbr_load_levels
    _tbr._load_levels = _patched_tbr_load_levels  # tbr imported the name; patch both bindings.

    streams: dict[str, list] = {k: [] for k in _STREAMS}
    anchor_hits: dict = defaultdict(lambda: defaultdict(list))  # date -> stream -> [(dir,conf,pnl)]
    realfills_inputs: dict[str, list] = {k: [] for k in _STREAMS}

    _reset_state()

    level_states: dict = {}
    ribbon_history: list = []
    last_date = None
    _lvl_cache = [None]
    _lvl_date = [None]
    _day_groups = {d: g.reset_index(drop=True) for d, g in rth.groupby(rth["timestamp_et"].dt.date)}

    for idx in range(len(rth)):
        bar = rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        bar_date = bar_time.date()
        if start and bar_date < start:
            continue
        if end and bar_date > end:
            continue
        if last_date is not None and bar_date != last_date:
            ribbon_history = []
            level_states = {}
        last_date = bar_date
        if idx < 60:
            continue
        try:
            r = ribbon_df.iloc[idx]
            ribbon_state = RibbonState(fast=float(r["fast"]), pivot=float(r["pivot"]),
                                       slow=float(r["slow"]), stack=str(r["stack"]),
                                       spread_cents=float(r["spread_cents"]))
        except Exception:
            continue
        ribbon_history.append(ribbon_state)
        ribbon_history = ribbon_history[-10:]
        vol_baseline = vol_baseline_20bar(rth, idx)
        range_baseline = range_baseline_20bar(rth, idx)
        vix_now = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 17.0
        vix_prior = float(vix_aligned.iloc[max(0, idx - 3)]) if max(0, idx - 3) < len(vix_aligned) else vix_now

        # Rebuild today's levels from history (no look-ahead: history <= bar_time).
        if bar_date != _lvl_date[0]:
            full_history = spy_full[spy_full["timestamp_et"] <= bar_time]
            _lvl_cache[0] = _detect_from_history(full_history, bar_date)
            _lvl_date[0] = bar_date
            # Build the ★★+ historical level dicts for TBR (shape the SHOTGUN detector expects).
            ls = _lvl_cache[0]
            lvl_prices = sorted(set(list(ls.active) + list(ls.multi_day)))
            _tbr_levels_by_date[bar_date.isoformat()] = [
                {"price": float(p), "label": "hist_level", "tier": None, "type": None, "stars": 2}
                for p in lvl_prices
            ]
        level_set = _lvl_cache[0]
        _update_level_states(level_states, level_set.active, bar, idx)
        htf = htf_stacks[idx] if idx < len(htf_stacks) else None
        _CUR_DATE[0] = bar_date.isoformat()  # so the no-arg TBR level monkeypatch sees today's levels

        ctx = BarContext(
            bar_idx=idx, timestamp_et=bar_time.to_pydatetime(), bar=bar,
            prior_bars=rth.iloc[:idx + 1], ribbon_now=ribbon_state, ribbon_history=ribbon_history,
            vix_now=vix_now, vix_prior=vix_prior, vol_baseline_20=vol_baseline,
            range_baseline_20=range_baseline, levels_active=level_set.active,
            multi_day_levels=level_set.multi_day, htf_15m_stack=htf, level_states=level_states,
        )
        day_bars = _day_groups[bar_date]
        bidx = int((day_bars["timestamp_et"] == bar_time).values.argmax())
        rb_dict = {"fast": ribbon_state.fast, "pivot": ribbon_state.pivot,
                   "slow": ribbon_state.slow, "spread_cents": ribbon_state.spread_cents,
                   "stack": ribbon_state.stack}

        # ── 1. TBR_HIGH_VOL_BEAR (SHOTGUN-style positional signature; bear side only) ──
        try:
            tbr_sig = _tbr.detect_tbr_high_vol_setup(
                bar=bar, day_bars=day_bars, bar_idx_in_day=bidx,
                ribbon_state_dict=rb_dict, vix_now=vix_now)
        except Exception as _e:
            sys.stderr.write(f"{_TBR} bar={bar_time}: {type(_e).__name__}: {_e}\n")
            tbr_sig = None
        if tbr_sig is not None and tbr_sig.direction == "short":
            _record(_TBR, tbr_sig, rth, idx, bar_date, vix_now, streams, anchor_hits,
                    realfills_inputs, bar)

        # ── 2. MOMENTUM_ACCELERATION_HIGHVOL_BEAR (ctx; bear side only) ──
        try:
            mom_sig = _mahv.detect_momentum_accel_highvol_setup(ctx)
        except Exception as _e:
            sys.stderr.write(f"{_MOM} bar={bar_time}: {type(_e).__name__}: {_e}\n")
            mom_sig = None
        if mom_sig is not None and mom_sig.direction == "short":
            _record(_MOM, mom_sig, rth, idx, bar_date, vix_now, streams, anchor_hits,
                    realfills_inputs, bar)

        # ── 3. VWAP_REJECTION_PRIME_BEAR (own signature, full RTH frame + global idx; bear side) ──
        try:
            vw_sig = _vw.detect_vwap_setup(
                bar=bar, bar_idx=idx, spy_bars=rth, ribbon_state=rb_dict)
        except Exception as _e:
            sys.stderr.write(f"{_VWAP} bar={bar_time}: {type(_e).__name__}: {_e}\n")
            vw_sig = None
        if vw_sig is not None and vw_sig.direction == "short":
            _record(_VWAP, vw_sig, rth, idx, bar_date, vix_now, streams, anchor_hits,
                    realfills_inputs, bar)

    # ── Per-stream blocks (dedup = first fire per (date,dir,conf)) ──
    def _rowsfmt(rows):
        return [{"pnl": r["pnl"], "date": r["date"]} for r in rows]

    stream_blocks = {}
    for name in _STREAMS:
        raw_rows = streams[name]
        ded = vbf2._dedup_local(raw_rows)
        distinct = sorted({r["date"] for r in ded})
        stream_blocks[name] = {
            "raw": vbf._stats(_rowsfmt(raw_rows)),
            "deduped": vbf._stats(_rowsfmt(ded)),
            "per_quarter_deduped": vbf._per_quarter(_rowsfmt(ded)),
            "distinct_dates": len(distinct),
        }

    # ── Anchor-day SPY-space block (OP-16 proxy; weak — real-fills is the authority) ──
    anchor_block = {}
    for d in sorted(ANCHORS):
        per_stream = {}
        for name in _STREAMS:
            fires = anchor_hits.get(d, {}).get(name, [])
            pnl = round(sum((f[2] or 0.0) for f in fires), 2)
            per_stream[name] = {"n": len(fires), "pnl": pnl}
        anchor_block[str(d)] = {"label": ANCHORS[d], **per_stream}

    result = {
        "window": f"{start}..{end}",
        "family": "bearish_continuation_structures",
        "patterns_bootstrapped": vbf._PATTERNS_BOOTSTRAPPED,
        "streams": stream_blocks,
        "anchor_days": anchor_block,
    }

    # ── Real-fills (PUTS, ATM + ITM2, chart-stop only) + anchor real-fills edge_capture + DSR ──
    if do_realfills:
        from lib.simulator_real import simulate_trade_real
        rf = {}
        rf_diag: dict = {}
        rf_anchor: dict = {}
        rf_dsr: dict = {}
        anchor_dates = {d.isoformat() for d in ANCHORS}
        anchor_labels = {d.isoformat(): ANCHORS[d] for d in ANCHORS}
        for stream in _STREAMS:
            inputs = realfills_inputs[stream]
            # Cap at first 120 signals for runtime BUT always include every anchor-day signal
            # (mirrors vbf2 anchor-inclusive cap — else a high-frequency watcher's May-2026 anchor
            # fills would be silently dropped off the end of the first-120 slice).
            capped = list(inputs[:120])
            capped_idx = {c[0] for c in capped}
            for tup in inputs[120:]:
                _idx, _bar, _sig = tup
                if str(_bar["timestamp_et"].date()) in anchor_dates and _idx not in capped_idx:
                    capped.append(tup)
                    capped_idx.add(_idx)
            for label, offset in _OFFSETS:
                rows = []
                anchor_rows = []  # (date, label, pnl)
                pnls = []         # for DSR (full-window per-trade $ P&L)
                n_attempted = n_no_fill = n_errored = 0
                for (idx, bar, sig) in capped:
                    n_attempted += 1
                    side = "P"  # all bearish-continuation = puts
                    rej = (sig.metadata.get("rejection_level")
                           or sig.metadata.get("break_level")
                           or sig.metadata.get("target_level")
                           or sig.metadata.get("rejection_low")
                           or sig.metadata.get("vwap_at_bar")
                           or sig.stop_price)
                    bar_date_str = str(bar["timestamp_et"].date())
                    try:
                        fill = simulate_trade_real(
                            entry_bar_idx=idx, entry_bar=bar, spy_df=rth, ribbon_df=ribbon_df,
                            rejection_level=float(rej), triggers_fired=sig.triggers_fired,
                            side=side, qty=3, setup=sig.setup_name,
                            premium_stop_pct=-0.99, strike_offset=offset)
                    except Exception as _e:
                        n_errored += 1
                        if n_errored <= 3:
                            sys.stderr.write(
                                f"real-fills {stream}_{label} bar={bar['timestamp_et']}: "
                                f"{type(_e).__name__}: {_e}\n")
                        fill = None
                    if fill is not None and getattr(fill, "dollar_pnl", None) is not None:
                        pnl = float(fill.dollar_pnl)
                        rows.append({"pnl": pnl, "date": bar_date_str})
                        pnls.append(pnl)
                        if bar_date_str in anchor_dates:
                            anchor_rows.append((bar_date_str, anchor_labels[bar_date_str], pnl))
                    else:
                        n_no_fill += 1
                rf[f"{stream}_{label}"] = vbf._stats(rows)
                rf_diag[f"{stream}_{label}"] = {
                    "attempted": n_attempted, "filled": len(rows),
                    "no_fill_or_no_data": n_no_fill, "errored": n_errored,
                }
                # Anchor-day real-fills edge_capture (the OP-16 authority on real P&L).
                win_pnl = sum(p for (_d, lab, p) in anchor_rows if lab == "WIN")
                loss_loss = sum(max(0.0, -p) for (_d, lab, p) in anchor_rows if lab == "LOSS")
                rf_anchor[f"{stream}_{label}"] = {
                    "n_anchor_fills": len(anchor_rows),
                    "win_day_pnl": round(win_pnl, 2),
                    "loss_day_loss": round(loss_loss, 2),
                    "edge_capture_realfills": round(win_pnl - loss_loss, 2),
                    "fills": [{"date": d, "label": lab, "pnl": round(p, 2)} for (d, lab, p) in anchor_rows],
                }
                rf_dsr[f"{stream}_{label}"] = _dsr_for(pnls)
        result["real_fills_capped"] = rf
        result["real_fills_diagnostics"] = rf_diag
        result["anchor_real_fills"] = rf_anchor
        result["dsr_gate"] = rf_dsr

    return result


def _record(name, sig, rth, idx, bar_date, vix_now, streams, anchor_hits, realfills_inputs, bar):
    """Grade a signal (SPY-space proxy) and record it into all collectors."""
    out, pnl = vbf._grade(sig, rth, idx, bar_date)
    streams[name].append(
        {"date": str(bar_date), "conf": sig.confidence, "dir": sig.direction,
         "out": out, "pnl": pnl, "vix": round(vix_now, 1)})
    if bar_date in ANCHORS:
        anchor_hits[bar_date][name].append((sig.direction, sig.confidence, pnl))
    realfills_inputs[name].append((idx, bar, sig))


def _dsr_for(pnls: list[float]) -> dict:
    """Advisory DSR/PSR on per-trade dollar P&L (constant qty=3 notional -> comparable).

    PBO skipped (no CSCV per-slice matrix). Matches sweep_timecond_exit._dsr_for. n_trials=N_TRIALS
    (the three structures searched). gate.py is ADVISORY (not a hard gate); a FAIL here is one of the
    three PROMOTE conditions failing.
    """
    if len(pnls) < 2:
        return {"verdict": "FAIL", "reason": f"n={len(pnls)} < 2", "dsr": None, "psr": None,
                "low_power": True, "n_obs": len(pnls)}
    try:
        res = evaluate_candidate(pnls, n_trials=N_TRIALS)
    except Exception as _e:
        return {"verdict": "FAIL", "reason": f"{type(_e).__name__}: {_e}", "dsr": None,
                "psr": None, "low_power": True, "n_obs": len(pnls)}
    return {"verdict": res.verdict, "dsr": round(res.dsr, 4), "psr": round(res.psr, 4),
            "pbo": res.pbo, "n_obs": res.n_obs, "low_power": res.low_power}


def _verdict(name: str, block: dict, rf: dict, rf_anchor: dict, rf_dsr: dict, anchor_block: dict) -> str:
    """Per-structure verdict. PROMOTE-CANDIDATE requires ALL of:
        full-window real-fills ATM exp > 0
        REAL-FILLS anchor edge_capture (ATM) > 0  (captures J's days, doesn't profit on his losses)
        DSR not FAIL.
    The real-fills anchor edge is the OP-16 authority (real option P&L on J's days); the SPY-space
    proxy is shown for context only.
    """
    ded = block["deduped"]
    n, wr, exp = ded["n"], ded["wr"], ded["exp"]
    atm = (rf or {}).get(f"{name}_ATM")
    itm = (rf or {}).get(f"{name}_ITM2")
    rf_str = ""
    rf_atm_pass = None
    if atm and atm["n"] > 0:
        rf_str = f" Full-window real-fills ATM exp ${atm['exp']} (N={atm['n']}, WR {atm['wr']}%)."
        if itm and itm["n"] > 0:
            rf_str += f" ITM2 exp ${itm['exp']} (N={itm['n']}, WR {itm['wr']}%)."
        rf_atm_pass = atm["exp"] > 0

    # SPY-space proxy edge (context only).
    _, _, spy_edge, _ = vbf._anchor_capture(anchor_block, name)
    rfa_atm = (rf_anchor or {}).get(f"{name}_ATM", {})
    rfa_itm = (rf_anchor or {}).get(f"{name}_ITM2", {})
    rfa_edge = rfa_atm.get("edge_capture_realfills")
    rfa_n = rfa_atm.get("n_anchor_fills", 0)
    dsr = (rf_dsr or {}).get(f"{name}_ATM", {})
    dsr_v = dsr.get("verdict")
    anchor_str = (f" REAL-FILLS anchor edge_capture: ATM ${rfa_edge} (n_anchor_fills={rfa_n}), "
                  f"ITM2 ${rfa_itm.get('edge_capture_realfills')} (n={rfa_itm.get('n_anchor_fills', 0)}). "
                  f"[SPY-space proxy edge ${spy_edge}.] DSR ATM={dsr_v} (dsr={dsr.get('dsr')}).")

    if n == 0 and (atm is None or atm["n"] == 0):
        return f"NO-FIRE — detector returned 0 signals over the window (bear side).{anchor_str}"
    # Gate on the REAL-FILLS anchor edge (the authority).
    if rfa_edge is None or rfa_n == 0:
        return (f"WATCH-ONLY / NO-ANCHOR-COVERAGE — fired on 0 of J's anchor days with OPRA fills; "
                f"cannot confirm it captures J's edge.{anchor_str}{rf_str}")
    if rfa_edge < 0:
        return (f"DO-NOT-PROMOTE / ANTI-EDGE — REAL-FILLS anchor edge_capture ${rfa_edge} < 0 "
                f"(bleeds on / profits against J's days).{anchor_str}{rf_str}")
    # rfa_edge > 0: captures J's edge on real fills. Now the broad-profitability + DSR gates.
    dsr_fail = (dsr_v == "FAIL")
    if rf_atm_pass is True and not dsr_fail:
        return (f"PROMOTE-CANDIDATE — REAL-FILLS anchor edge ${rfa_edge} > 0, full-window real-fills "
                f"ATM exp > 0, DSR {dsr_v}.{rf_str}{anchor_str}")
    if rf_atm_pass is True and dsr_fail:
        return (f"WATCH-ONLY / DSR-FAIL — anchor edge ${rfa_edge} > 0 and full-window ATM positive, "
                f"but DSR FAIL (selection/over-fit risk).{rf_str}{anchor_str}")
    if rf_atm_pass is False:
        return (f"WATCH-ONLY / EDGE-ALIGNED-BUT-FRAGILE — REAL-FILLS anchor edge ${rfa_edge} > 0 "
                f"(captures J's days) BUT full-window real-fills ATM negative/thin "
                f"(regime-fragile, C24).{rf_str}{anchor_str}")
    return (f"WATCH-ONLY — REAL-FILLS anchor edge ${rfa_edge} > 0; full-window real-fills "
            f"inconclusive.{rf_str}{anchor_str}")


def _ranking(result: dict) -> list[dict]:
    """Rank by REAL-FILLS anchor edge_capture (primary) then full-window real-fills ATM exp."""
    rf = result.get("real_fills_capped", {})
    rf_anchor = result.get("anchor_real_fills", {})
    rf_dsr = result.get("dsr_gate", {})
    anchor_block = result.get("anchor_days", {})
    rows = []
    for name in _STREAMS:
        ded = result["streams"][name]["deduped"]
        atm = rf.get(f"{name}_ATM", {})
        itm = rf.get(f"{name}_ITM2", {})
        rfa_atm = rf_anchor.get(f"{name}_ATM", {})
        rfa_itm = rf_anchor.get(f"{name}_ITM2", {})
        _, _, spy_edge, spy_anti = vbf._anchor_capture(anchor_block, name)
        rows.append({
            "pattern": name,
            "realfills_anchor_edge_atm": rfa_atm.get("edge_capture_realfills"),
            "realfills_anchor_edge_itm2": rfa_itm.get("edge_capture_realfills"),
            "realfills_anchor_n": rfa_atm.get("n_anchor_fills", 0),
            "spy_space_anchor_edge_proxy": spy_edge,
            "spy_space_anti_correlated": spy_anti,
            "spy_n": ded["n"], "spy_wr": ded["wr"], "spy_exp": ded["exp"],
            "realfills_atm_exp": atm.get("exp"), "realfills_atm_n": atm.get("n", 0),
            "realfills_atm_wr": atm.get("wr"), "realfills_atm_total": atm.get("total"),
            "realfills_itm2_exp": itm.get("exp"), "realfills_itm2_n": itm.get("n", 0),
            "realfills_itm2_wr": itm.get("wr"),
            "dsr_atm_verdict": rf_dsr.get(f"{name}_ATM", {}).get("verdict"),
            "dsr_atm": rf_dsr.get(f"{name}_ATM", {}).get("dsr"),
            "note": _VARIANT_NOTES.get(name, ""),
        })

    def _key(r):
        rfa = r["realfills_anchor_edge_atm"]
        rfa = rfa if rfa is not None else -1e9
        rfe = r["realfills_atm_exp"]
        rfe = rfe if rfe is not None else -1e9
        return (rfa > 0, rfa, rfe)
    rows.sort(key=_key, reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def _op20_disclosures() -> dict:
    return {
        "authority": ("Real-fills (simulate_trade_real over OPRA bars, valid through ~2026-05-29) is "
                      "the WR/expectancy authority. SPY-space grade_observation is a directional proxy "
                      "(SPY move x 100), NOT option P&L (C1/C3)."),
        "levels": ("Historically-rebuilt ★★ proxies (active+multi_day from _detect_from_history as-of "
                   "each day), NOT production ★★★ named levels. No key-levels archive covers the window "
                   "so a true ★★★ historical validation is impossible (OP-20). Break/ribbon/structure "
                   "logic uses clean ctx.prior_bars (no look-ahead)."),
        "tbr_lookahead_fix": ("tbr_high_vol_watcher reads automation/state/key-levels.json (TODAY's "
                              "levels) via shotgun_scalper_watcher._load_levels — a look-ahead trap for "
                              "a 16-month replay. NEUTRALIZED here by monkeypatching _load_levels to "
                              "historically-detected ★★+ levels per bar-date. The detector also "
                              "auto-derives intraday levels (auto_derive_intraday_levels=True), so the "
                              "trendline path is exercised regardless of named levels."),
        "anchor_metric": ("OP-16 edge_capture = sum(P&L on WIN anchors 4/29,5/01,5/04) - "
                          "sum(max(0,-P&L) on LOSS anchors 5/05,5/06,5/07). PRIMARY ranking key, "
                          "computed on REAL fills (anchor_real_fills block) — the authority. PROMOTE "
                          "requires REAL-FILLS anchor edge_capture > 0 AND full-window real-fills ATM "
                          "exp > 0 AND DSR not FAIL."),
        "direction_filter": ("All three watchers can fire either direction; this harness keeps only "
                             "direction=='short' (bearish CONTINUATION). The bull-side fires are out "
                             "of scope (a different, non-bearish question)."),
        "real_fills_model": ("simulate_trade_real, side=P (all bearish-continuation = puts), qty=3, "
                             "chart-stop only (premium_stop_pct=-0.99 per L51/L55), ATM (offset 0) and "
                             "ITM2 (offset -2). Cap = first 120 signals/stream, ANCHOR-INCLUSIVE (every "
                             "anchor-day signal always simulated). Real-fills N counts RAW signals "
                             "(pre-dedup); compare WR/exp, not N, vs the SPY-space deduped N. NOTE: TBR "
                             "is single-exit in production (no runner); here it is graded with the SAME "
                             "TP1+runner real-fills model as the rest of the family so edge_capture is "
                             "apples-to-apples — the production single-exit P&L will differ."),
        "dsr_gate": (f"Advisory DSR/PSR (Bailey & Lopez de Prado) on per-trade $ P&L, n_trials="
                     f"{N_TRIALS} (structures searched). PBO skipped (no CSCV matrix). gate.py is NOT a "
                     f"hard production gate; a DSR FAIL is treated as one PROMOTE condition failing. "
                     f"Small-sample low_power flagged when n_obs<20 (C24)."),
        "prior_research": ("Sequel to analysis/recommendations/bearish-continuation-family.json "
                           "(research #26, level-rejection family). That run found BEARISH_REJECTION_"
                           "MORNING is the ONLY edge-aligned entry (anchor edge +$134 ATM/+$197 ITM2, "
                           "full-window exp NEGATIVE -> edge-aligned-but-fragile) and every other "
                           "level-rejection variant anti-edge / zero-coverage. THIS run extends the "
                           "question to non-level-rejection STRUCTURES."),
        "scope": ("Three bearish-continuation STRUCTURES only (lean, per task): TBR_HIGH_VOL "
                  "(trendline-break-retest), MOMENTUM_ACCELERATION_HIGHVOL (momentum continuation), "
                  "VWAP_REJECTION_PRIME (session-VWAP rejection). No new detectors built."),
    }


def _build(result: dict) -> dict:
    rf = result.get("real_fills_capped", {})
    rf_anchor = result.get("anchor_real_fills", {})
    rf_dsr = result.get("dsr_gate", {})
    anchor_block = result.get("anchor_days", {})
    result["verdict"] = {name: _verdict(name, result["streams"][name], rf, rf_anchor, rf_dsr, anchor_block)
                         for name in _STREAMS}
    result["ranking"] = _ranking(result)
    result["op20_disclosures"] = _op20_disclosures()
    promote = [r for r in result["ranking"]
               if "PROMOTE-CANDIDATE" in result["verdict"][r["pattern"]]]
    edge_aligned = [r for r in result["ranking"]
                    if (r["realfills_anchor_edge_atm"] or -1) > 0]
    result["headline"] = {
        "tested_structures": _STREAMS,
        "promote_candidates": [r["pattern"] for r in promote],
        "edge_aligned_on_real_fills": [r["pattern"] for r in edge_aligned],
        "verdict": _conclusion(result, promote, edge_aligned),
    }
    return result


def _conclusion(result: dict, promote: list[dict], edge_aligned: list[dict]) -> str:
    ranking = result["ranking"]
    least_bad = ranking[0]["pattern"] if ranking else "(none)"
    if promote:
        names = ", ".join(r["pattern"] for r in promote)
        return (f"NEW EDGE-ALIGNED STRUCTURE FOUND: {names}. Clears POSITIVE real-fills anchor "
                f"edge_capture AND positive full-window real-fills ATM AND DSR not FAIL. Cross-check "
                f"vs j_edge_tracker (full engine) before any params change (Rule 9).")
    aligned = ", ".join(r["pattern"] for r in edge_aligned) or "(none)"
    return (
        f"CONCLUSIVE — NO bearish-continuation STRUCTURE beyond BEARISH_REJECTION is edge-aligned + "
        f"worth building on. Across the trendline (TBR_HIGH_VOL), momentum "
        f"(MOMENTUM_ACCELERATION_HIGHVOL) and VWAP (VWAP_REJECTION_PRIME) families, none clears the "
        f"PROMOTE gate (positive real-fills ATM exp AND positive real-fills anchor edge_capture AND "
        f"DSR not FAIL). Structures with a POSITIVE real-fills anchor edge (capture J's days) but not "
        f"broadly profitable: {aligned}. Least-bad / closest: {least_bad}. This NARROWS THE FIELD: "
        f"combined with research #26 (level-rejection family), the ONLY entry that captures J's anchor "
        f"days on real fills remains BEARISH_REJECTION_RIDE_THE_RIBBON. The leverage is EXIT/REGIME "
        f"work on that one entry, not a new bearish-continuation entry structure. No PROMOTE.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2026-06-16")
    ap.add_argument("--realfills", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end), a.realfills)
    res = _build(res)
    txt = json.dumps(res, indent=2, default=str)
    print(txt)
    if a.out:
        outp = Path(a.out)
        if not outp.is_absolute():
            outp = (Path.cwd() / outp).resolve()
        outp.write_text(txt, encoding="utf-8")
        print("wrote", outp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
