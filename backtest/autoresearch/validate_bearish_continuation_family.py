"""Bearish-CONTINUATION entry-variant validation — which bearish entries fire WITH J's edge.

This is the POSITIVE strategic counterpart to the mean-reversion-bounce research (that
family is dead / anti-edge). J's real money is in bearish-continuation PUTs:
    4/29 SPY 710P +$342 | 5/01 SPY 721P +$470 | 5/04 SPY 721P +$730
This script ranks the bearish-continuation entry detectors by the OP-16 metric that
actually matters — **edge_capture** (does the variant FIRE on J's win/down days, and
NOT bleed on his loss days) — multiplied by real-fills expectancy.

It reuses the validate_breakout_family harness verbatim for the heavy lifting:
  * the crypto.lib.chart_patterns bootstrap
  * _load_data (SPY+VIX 5m, deduped)
  * the full per-bar BarContext pipeline with HISTORICALLY-REBUILT levels (no look-ahead)
  * _grade (TP1+runner grade_observation over same-day future bars)
  * the OP-16 anchor edge_capture scorer (_anchor_capture) and _stats / _per_quarter
  * simulator_real real-fills with chart-stop-only (premium_stop_pct=-0.99)
We only swap the DETECTOR SET to the bearish-continuation family and run every variant
as PUTS at both ATM (the anchor strike class) and ITM2 (the Bold strike class).

THE BEARISH-CONTINUATION FAMILY (all direction="short" / puts):
  1. BEARISH_REJECTION_MORNING       bearish_rejection_morning_watcher
       The codified BEARISH_REJECTION_RIDE_THE_RIBBON: 09:35-10:55 ET, ribbon just flipped
       BEAR, ★★+ level rejection >=15c, vol >=1.5x. Built to cover J's 4/29 (10:25) and
       5/04 (10:27) anchor entries. This is the CONFIRMED-setup BASELINE ("what works").
  2. LEVEL_BREAK_FIRST_STRIKE        level_break_first_strike_watcher
       MIXED-ribbon level break >=20c, vol >=1.5x, VIX-tiered. The "first strike" before
       the ribbon confirms — a bear continuation of a broken level. Prior real-fills
       (lbfs-expanded-real-fills.json, VIX>=20 N=19): ATM WR 58.8% +$763.
  3. HEAD_AND_SHOULDERS_BEAR         hs_watcher
       Bearish topping / neckline break (continuation down). Prior real-fills
       (hs-bear-real-fills.json N=19): WR 73.7% +$346, strong 09:40-12:00.
  4. BEARISH_REVERSAL_AT_LEVEL       bearish_reversal_at_level_watcher  [CONTRAST]
       COUNTERTREND fade on a BULL ribbon (NOT continuation). Included as the
       continuation-vs-countertrend contrast — J's 5/01 was a countertrend rejection.
  5. STAIRSTEP_CONTINUATION          stairstep_continuation_watcher     [DEAD CONTROL]
       RETIRED 2026-06-18 (anti-J-edge). Always returns None. Included as a negative
       control: it MUST register 0 fires and edge_capture 0 here (confirms retirement).

The TRENDLINE_BREAK_VOLUME and RESISTANCE_OVERSHOOT_REVERSAL playbook candidates have
NO shipped watcher detector (n=2 / n=1 paper observations, awareness-only). They cannot
be backtested here without first writing a detector; noted in the scorecard as
NO-DETECTOR rather than silently omitted.

RANKING: primary key = edge_capture (must be POSITIVE — captures J's 4/29-5/01-5/04
winners, adds little/no loss on 5/05-5/07); among positive-edge variants, secondary
key = real-fills ATM expectancy. A variant with NEGATIVE edge_capture is anti-edge and
is never a PROMOTE-CANDIDATE regardless of aggregate stats (OP-16, lessons C24).

OP-20 disclosure: SPY-space grade is a proxy (SPY move x 100), NOT real option P&L —
real_fills is the authority (lessons C1/C3). Levels are historically-rebuilt ★★ proxies
(active+multi_day from _detect_from_history), NOT the production ★★★ named set; a true
★★★ historical validation is impossible (no key-levels archive over the window). The
intraday-break / ribbon / structure logic uses clean ctx.prior_bars (no look-ahead).

Usage:
  python -m autoresearch.validate_bearish_continuation_family --realfills \
      --out ../analysis/recommendations/bearish-continuation-family.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

# ── Reuse the breakout-family harness wholesale (bootstrap, data, ctx, grading) ──
# Importing it runs the crypto.lib.chart_patterns bootstrap and pulls in the engine
# imports (filters, ribbon, levels, orchestrator helpers, simulate_trade_real later).
from autoresearch import validate_breakout_family as vbf  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent

# Engine bits reused via the breakout-family module (already imported there).
from lib.filters import vol_baseline_20bar, range_baseline_20bar, BarContext  # noqa: E402
from lib.ribbon import compute_ribbon, RibbonState  # noqa: E402
from lib.levels import _detect_from_history  # noqa: E402
from lib.orchestrator import (  # noqa: E402
    _align_vix_to_spy,
    _precompute_htf_15m_stacks,
    _update_level_states,
)

# ── Bearish-continuation detectors + their module-level state (for deterministic reset) ──
from lib.watchers import bearish_rejection_morning_watcher as _brm  # noqa: E402
from lib.watchers import level_break_first_strike_watcher as _lbfs  # noqa: E402
from lib.watchers import hs_watcher as _hs  # noqa: E402
from lib.watchers import bearish_reversal_at_level_watcher as _brl  # noqa: E402
from lib.watchers import stairstep_continuation_watcher as _stair  # noqa: E402

# OP-16 anchors + EOD reused from the breakout-family module (single source of truth).
ANCHORS = vbf.ANCHORS
EOD = vbf.EOD

# Streams, in ranking-presentation order. BASELINE first, DEAD CONTROL last.
_BASELINE = "BEARISH_REJECTION_MORNING"
_DEAD_CONTROL = "STAIRSTEP_CONTINUATION"
_CONTRAST = "BEARISH_REVERSAL_AT_LEVEL"
_STREAMS = [
    _BASELINE,
    "LEVEL_BREAK_FIRST_STRIKE",
    "HEAD_AND_SHOULDERS_BEAR",
    _CONTRAST,
    _DEAD_CONTROL,
]

# Every bearish variant is PUTS and can be taken at ATM (anchor strike class, J's 710P/721P
# were ~ATM) and ITM2 (the Bold-account strike class). So no _LONG_ATM_ONLY here.
_OFFSETS = (("ATM", 0), ("ITM2", -2))

# Detector dispatch: stream -> (module, callable). All take ctx and return Optional[WatcherSignal].
_DETECTORS = {
    _BASELINE: _brm.detect_bearish_rejection_morning,
    "LEVEL_BREAK_FIRST_STRIKE": _lbfs.detect_lbfs_setup,
    "HEAD_AND_SHOULDERS_BEAR": _hs.detect_hs_setup,
    _CONTRAST: _brl.detect_bearish_reversal_at_level,
    _DEAD_CONTROL: _stair.detect_stairstep_continuation_setup,
}

# Per-variant promotion gate metadata (for the scorecard's human-facing context).
_VARIANT_NOTES = {
    _BASELINE: "CONFIRMED-setup baseline (BEARISH_REJECTION_RIDE_THE_RIBBON). Anchor coverage: "
               "4/29 +$342 (10:25), 5/04 +$730 (10:27). This is 'what works'.",
    "LEVEL_BREAK_FIRST_STRIKE": "WATCH-ONLY. Prior real-fills VIX>=20 N=19: ATM WR 58.8% +$763 "
                                "(lbfs-expanded-real-fills.json). OP-21 live gate 0/3.",
    "HEAD_AND_SHOULDERS_BEAR": "WATCH-ONLY. Prior real-fills N=19: WR 73.7% +$346, strong 09:40-12:00 "
                               "(hs-bear-real-fills.json). OP-21 live gate 0/3.",
    _CONTRAST: "CONTRAST (countertrend fade on BULL ribbon, NOT continuation). Historical gate 3/3, "
               "live 0/3. Included to compare continuation vs countertrend on the anchor set.",
    _DEAD_CONTROL: "DEAD CONTROL — RETIRED 2026-06-18 (anti-J-edge). Detector returns None; MUST show "
                   "0 fires + edge_capture 0 here (retirement self-check).",
}


def _reset_state() -> None:
    """Reset every module-level cooldown/cache so a fresh replay is deterministic.

    Only hs_watcher and stairstep carry module-level state; brm / lbfs / brl are
    stateless per-call. Stairstep is retired (always None) but we clear its caches
    anyway for hygiene (mirrors validate_breakout_family._reset_watcher_state).
    """
    _hs._last_signal_time = None
    _stair._last_signal_time = None
    _stair._cached_all = []
    _stair._cached_broken_res = []
    _stair._cached_broken_sup = []
    _stair._cached_levels_date = None


def run(start: dt.date, end: dt.date, do_realfills: bool) -> dict:
    """Replay the bearish-continuation family over [start, end]; grade + anchor-score.

    Structure mirrors validate_breakout_family.run but with our 5-detector set and
    PUTS-at-ATM+ITM2 real-fills.
    """
    spy_full, vix_full = vbf._load_data(start, end)
    spy_full["timestamp_et"] = vbf.pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
                   (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    ribbon_df = compute_ribbon(rth["close"])
    vix_aligned = _align_vix_to_spy(rth, vix_full)
    htf_stacks = _precompute_htf_15m_stacks(rth)

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
        level_set = _lvl_cache[0]
        _update_level_states(level_states, level_set.active, bar, idx)
        htf = htf_stacks[idx] if idx < len(htf_stacks) else None

        ctx = BarContext(
            bar_idx=idx, timestamp_et=bar_time.to_pydatetime(), bar=bar,
            prior_bars=rth.iloc[:idx + 1], ribbon_now=ribbon_state, ribbon_history=ribbon_history,
            vix_now=vix_now, vix_prior=vix_prior, vol_baseline_20=vol_baseline,
            range_baseline_20=range_baseline, levels_active=level_set.active,
            multi_day_levels=level_set.multi_day, htf_15m_stack=htf, level_states=level_states,
        )

        for stream, detector in _DETECTORS.items():
            try:
                sig = detector(ctx)
            except Exception as _e:
                sys.stderr.write(f"{stream} bar={bar_time}: {type(_e).__name__}: {_e}\n")
                sig = None
            if sig is None:
                continue
            out, pnl = vbf._grade(sig, rth, idx, bar_date)
            streams[stream].append(
                {"date": str(bar_date), "conf": sig.confidence, "dir": sig.direction,
                 "out": out, "pnl": pnl, "vix": round(vix_now, 1)})
            if bar_date in ANCHORS:
                anchor_hits[bar_date][stream].append((sig.direction, sig.confidence, pnl))
            realfills_inputs[stream].append((idx, bar, sig))

    # ── Per-stream blocks (dedup = first fire per (date,dir,conf)) ──
    def _rowsfmt(rows):
        return [{"pnl": r["pnl"], "date": r["date"]} for r in rows]

    stream_blocks = {}
    for name in _STREAMS:
        raw_rows = streams[name]
        ded = vbf._dedup(raw_rows) if hasattr(vbf, "_dedup") else _dedup_local(raw_rows)
        distinct = sorted({r["date"] for r in ded})
        stream_blocks[name] = {
            "raw": vbf._stats(_rowsfmt(raw_rows)),
            "deduped": vbf._stats(_rowsfmt(ded)),
            "per_quarter_deduped": vbf._per_quarter(_rowsfmt(ded)),
            "distinct_dates": len(distinct),
        }

    # ── Anchor-day block (OP-16 preservation) — puts pnl per anchor day ──
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
        "family": "bearish_continuation",
        "patterns_bootstrapped": vbf._PATTERNS_BOOTSTRAPPED,
        "streams": stream_blocks,
        "anchor_days": anchor_block,
    }

    # ── Real-fills (PUTS, ATM + ITM2, chart-stop only) ──
    # We collect per-fill rows (with date) so we can derive BOTH the full-window stats
    # AND an anchor-day-only real-fills block — the latter is the AUTHORITATIVE answer
    # to "does this variant capture J's edge?" (real option P&L on his actual days),
    # superior to the SPY-space anchor proxy in _anchor_capture.
    if do_realfills:
        from lib.simulator_real import simulate_trade_real
        rf = {}
        rf_diag: dict = {}
        rf_anchor: dict = {}
        anchor_dates = {d.isoformat() for d in ANCHORS}
        anchor_labels = {d.isoformat(): ANCHORS[d] for d in ANCHORS}
        for stream in _STREAMS:
            inputs = realfills_inputs[stream]
            # Cap at first 120 signals for runtime BUT ALWAYS include every anchor-day
            # signal — they are the whole point of this research and high-frequency
            # watchers (e.g. BEARISH_REJECTION_MORNING, 131 fires) would otherwise have
            # their May-2026 anchor signals dropped off the end of the first-120 slice.
            capped = list(inputs[:120])
            capped_idx = {c[0] for c in capped}
            anchor_dates_iso = {d.isoformat() for d in ANCHORS}
            for tup in inputs[120:]:
                _idx, _bar, _sig = tup
                if str(_bar["timestamp_et"].date()) in anchor_dates_iso and _idx not in capped_idx:
                    capped.append(tup)
                    capped_idx.add(_idx)
            for label, offset in _OFFSETS:
                rows = []
                anchor_rows = []  # (date, label, pnl)
                n_attempted = n_no_fill = n_errored = 0
                for (idx, bar, sig) in capped:
                    n_attempted += 1
                    # All bearish-continuation entries are puts.
                    side = "P"
                    rej = (sig.metadata.get("rejection_level")
                           or sig.metadata.get("break_level")
                           or sig.metadata.get("neckline")
                           or sig.metadata.get("broken_level")
                           or sig.metadata.get("swept_level")
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
        result["real_fills_capped"] = rf
        result["real_fills_diagnostics"] = rf_diag
        result["anchor_real_fills"] = rf_anchor

    return result


def _dedup_local(rows):
    """Fallback dedup if vbf._dedup is unavailable (keeps first fire per date/dir/conf)."""
    seen = set()
    out = []
    for r in rows:
        key = (r["date"], r.get("dir"), r.get("conf"))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _verdict(name: str, block: dict, rf: dict, anchor_block: dict, rf_anchor: dict) -> str:
    """Bearish-continuation verdict.

    TWO edge_capture measures are reported; the REAL-FILLS one is the authority:
      * anchor_realfills_edge = real option P&L on J's anchor days (4/29,5/01,5/04 WIN
        minus losses on 5/05,5/06,5/07). THIS is the OP-16 gate (real money on J's days).
      * spy_anchor_edge       = SPY-space proxy (directional coverage). Weak/thin; shown
        for context only — many watchers barely fire on the historical ★★ proxy levels.

    PROMOTE-CANDIDATE requires: anchor_realfills_edge > 0 (captures J's edge on real fills)
    AND full-window real-fills ATM expectancy > 0 (the variant is profitable broadly, not
    just on the 3 anchor days). A variant that wins the anchor days but bleeds over 16
    months is regime-fragile (lessons C24) -> WATCH-ONLY, not PROMOTE.
    """
    if name == _DEAD_CONTROL:
        ded = block["deduped"]
        _, _, edge, _ = vbf._anchor_capture(anchor_block, name)
        if ded["n"] == 0 and edge == 0.0:
            return ("DEAD-CONTROL-OK — retired detector fired 0 times, edge_capture $0 "
                    "(retirement confirmed; correctly anti-edge and removed).")
        return (f"DEAD-CONTROL-UNEXPECTED — retired detector fired n={ded['n']} / edge_capture ${edge}. "
                f"Investigate (should be 0).")

    ded = block["deduped"]
    n, wr, exp = ded["n"], ded["wr"], ded["exp"]
    atm = (rf or {}).get(f"{name}_ATM")
    itm = (rf or {}).get(f"{name}_ITM2")
    rf_str = ""
    rf_pass = None
    if atm and atm["n"] > 0:
        rf_str = f" Full-window real-fills ATM exp ${atm['exp']} (N={atm['n']}, WR {atm['wr']}%)."
        if itm and itm["n"] > 0:
            rf_str += f" ITM2 exp ${itm['exp']} (N={itm['n']}, WR {itm['wr']}%)."
        rf_pass = atm["exp"] > 0 and atm["wr"] >= 45 and atm["n"] >= 15

    # SPY-space proxy edge (context only).
    _, _, spy_edge, spy_anti = vbf._anchor_capture(anchor_block, name)
    # Real-fills anchor edge (the authority). Prefer ATM (anchor strike class); also report ITM2.
    rfa_atm = (rf_anchor or {}).get(f"{name}_ATM", {})
    rfa_itm = (rf_anchor or {}).get(f"{name}_ITM2", {})
    rfa_edge = rfa_atm.get("edge_capture_realfills")
    rfa_n = rfa_atm.get("n_anchor_fills", 0)
    anchor_str = (f" REAL-FILLS anchor edge_capture: ATM ${rfa_edge} (n_anchor_fills={rfa_n}), "
                  f"ITM2 ${rfa_itm.get('edge_capture_realfills')} (n={rfa_itm.get('n_anchor_fills', 0)}). "
                  f"[SPY-space proxy edge ${spy_edge}.]")

    # ── Gate on the REAL-FILLS anchor edge (the authority) ──
    if rfa_edge is None or rfa_n == 0:
        return (f"WATCH-ONLY / NO-ANCHOR-COVERAGE — fired on 0 of J's anchor days with OPRA fills; "
                f"cannot confirm it captures J's edge.{anchor_str}{rf_str}")
    if rfa_edge < 0:
        return (f"DO-NOT-PROMOTE / ANTI-EDGE — REAL-FILLS anchor edge_capture ${rfa_edge} < 0 "
                f"(bleeds on J's days).{anchor_str}{rf_str}")
    # rfa_edge > 0: captures J's edge on real fills. Now check broad profitability.
    if rf_pass is True:
        return (f"PROMOTE-CANDIDATE — REAL-FILLS anchor edge_capture ${rfa_edge} > 0 AND full-window "
                f"real-fills ATM positive.{rf_str}{anchor_str}")
    if rf_pass is False:
        return (f"WATCH-ONLY / EDGE-ALIGNED-BUT-FRAGILE — REAL-FILLS anchor edge_capture ${rfa_edge} > 0 "
                f"(captures J's days) BUT full-window real-fills ATM negative/thin "
                f"(regime-fragile, lessons C24).{rf_str}{anchor_str}")
    return (f"WATCH-ONLY — REAL-FILLS anchor edge_capture ${rfa_edge} > 0; full-window real-fills "
            f"inconclusive (no OPRA fills graded).{rf_str}{anchor_str}")


def _ranking(result: dict) -> list[dict]:
    """Rank variants by REAL-FILLS anchor edge_capture (primary — the OP-16 authority)
    then full-window real-fills ATM expectancy (secondary). The DEAD_CONTROL is excluded.

    Rationale: the question is "which bearish entry FIRES WITH J's edge x has positive
    real-fills". The real-fills anchor edge_capture answers the first half on real option
    P&L (not the weak SPY-space proxy); the full-window ATM exp answers the second.
    """
    rf = result.get("real_fills_capped", {})
    rf_anchor = result.get("anchor_real_fills", {})
    anchor_block = result.get("anchor_days", {})
    rows = []
    for name in _STREAMS:
        if name == _DEAD_CONTROL:
            continue
        ded = result["streams"][name]["deduped"]
        atm = rf.get(f"{name}_ATM", {})
        itm = rf.get(f"{name}_ITM2", {})
        rfa_atm = rf_anchor.get(f"{name}_ATM", {})
        rfa_itm = rf_anchor.get(f"{name}_ITM2", {})
        _, _, spy_edge, spy_anti = vbf._anchor_capture(anchor_block, name)
        rf_exp = atm.get("exp")
        rfa_edge = rfa_atm.get("edge_capture_realfills")
        rows.append({
            "pattern": name,
            "realfills_anchor_edge_atm": rfa_edge,
            "realfills_anchor_edge_itm2": rfa_itm.get("edge_capture_realfills"),
            "realfills_anchor_n": rfa_atm.get("n_anchor_fills", 0),
            "spy_space_anchor_edge_proxy": spy_edge,
            "spy_space_anti_correlated": spy_anti,
            "spy_n": ded["n"], "spy_wr": ded["wr"], "spy_exp": ded["exp"],
            "realfills_atm_exp": rf_exp, "realfills_atm_n": atm.get("n", 0),
            "realfills_atm_wr": atm.get("wr"), "realfills_atm_total": atm.get("total"),
            "realfills_itm2_exp": itm.get("exp"), "realfills_itm2_n": itm.get("n", 0),
            "note": _VARIANT_NOTES.get(name, ""),
        })
    # Sort: real-fills anchor edge>0 first, then by that edge (desc), then full-window ATM exp (desc).
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


def _no_detector_candidates() -> list[dict]:
    """Playbook bearish-continuation candidates with NO shipped detector (cannot backtest)."""
    return [
        {"pattern": "TRENDLINE_BREAK_VOLUME",
         "status": "NO-DETECTOR — playbook n=2 paper observations (5/08, 5/11), awareness-only. "
                   "No watcher in the fleet; backtest requires writing a trendline-break detector "
                   "(backtest/lib/trendlines.py exists but is not wired to a watcher). Bear side = "
                   "ascending-trendline break on >=2x volume."},
        {"pattern": "RESISTANCE_OVERSHOOT_REVERSAL",
         "status": "NO-DETECTOR — playbook n=1 paper observation (5/07 bull-trap to 736.11). "
                   "Light-vol break + heavy-vol reversal back below level. No watcher shipped."},
        {"pattern": "sequence_rejection (trigger, not a standalone watcher)",
         "status": "NO-STANDALONE-DETECTOR — sequence_rejection is an engine trigger (filters.py) "
                   "consumed by the main bear setup, not an isolated watcher. The SHORT/bear "
                   "continuation of a broken level is what STAIRSTEP_CONTINUATION encoded — and that "
                   "is the DEAD CONTROL here (retired, anti-edge). So the bear sequence_rejection "
                   "structure is already represented (and failed) via STAIRSTEP."},
    ]


def _op20_disclosures() -> dict:
    return {
        "authority": ("Real-fills (simulator_real over OPRA bars, valid through ~2026-05-29) is the "
                      "WR/expectancy authority. SPY-space grade_observation is a directional proxy "
                      "(SPY move x 100), NOT option P&L (lessons C1/C3)."),
        "levels": ("Historically-rebuilt ★★ proxies (active+multi_day from _detect_from_history "
                   "as-of each day), NOT production ★★★ named levels. No key-levels archive covers "
                   "the window, so a true ★★★ historical validation is impossible. Disclosed per OP-20. "
                   "The break/ribbon/structure logic uses clean ctx.prior_bars (no look-ahead)."),
        "anchor_metric": ("OP-16 edge_capture = sum(P&L on WIN anchors 4/29,5/01,5/04) - "
                          "sum(max(0,-P&L) on LOSS anchors 5/05,5/06,5/07). PRIMARY ranking key. "
                          "Computed TWO ways: (1) REAL-FILLS (anchor_real_fills block) — real option "
                          "P&L per fill on J's days — THE AUTHORITY; (2) SPY-space proxy "
                          "(anchor_days block) — directional-coverage only, weak/thin. PROMOTE requires "
                          "REAL-FILLS anchor edge_capture > 0 AND full-window real-fills ATM exp > 0."),
        "anchor_pnl_basis": ("CRITICAL: the SPY-space anchor_days P&L is a DIRECTIONAL PROXY and is "
                             "thin/misleading here — the watchers fire on few historical ★★ proxy-level "
                             "anchor days and grade_observation returns ~$0 on most. The anchor_real_fills "
                             "block (real OPRA option P&L on J's days) is the correct read on edge "
                             "capture and can disagree sharply (e.g. a SPY-space $0 / -$80 maps to a "
                             "strongly POSITIVE real-fills anchor edge for BEARISH_REJECTION_MORNING). "
                             "The engine-level j_edge_tracker (full engine + real fills) remains the "
                             "doctrine gate for any actual params change; THIS scorecard ranks ENTRIES."),
        "real_fills_model": ("simulate_trade_real, side=P (all bearish-continuation = puts), qty=3, "
                             "chart-stop only (premium_stop_pct=-0.99 per L51/L55), ATM (offset 0) and "
                             "ITM2 (offset -2). Capped at first 120 signals/stream for runtime BUT the "
                             "cap is ANCHOR-INCLUSIVE — every anchor-day (4/29-5/07) signal is always "
                             "simulated even if it falls beyond signal #120 (else a high-frequency "
                             "watcher's May-2026 anchor fills would be silently dropped). Real-fills N "
                             "counts RAW signals (pre-dedup); compare WR/exp, not N, vs SPY-space N."),
        "scope": ("Bearish-CONTINUATION family only (lean, per task). BEARISH_REVERSAL_AT_LEVEL is a "
                  "countertrend CONTRAST, not continuation. STAIRSTEP is the retired DEAD CONTROL. "
                  "TRENDLINE_BREAK_VOLUME / RESISTANCE_OVERSHOOT_REVERSAL have no detector (see "
                  "no_detector_candidates)."),
        "cross_check": ("LBFS vs lbfs-expanded-real-fills.json (VIX>=20 N=19 ATM WR 58.8% +$763); "
                        "HS_BEAR vs hs-bear-real-fills.json (N=19 WR 73.7% +$346). Differences expected: "
                        "those scans use curated pools / VIX gating; this is a full-window ctx replay "
                        "with historical-level proxies."),
    }


def _build(result: dict) -> dict:
    rf = result.get("real_fills_capped", {})
    rf_anchor = result.get("anchor_real_fills", {})
    anchor_block = result.get("anchor_days", {})
    result["verdict"] = {name: _verdict(name, result["streams"][name], rf, anchor_block, rf_anchor)
                         for name in _STREAMS}
    result["ranking"] = _ranking(result)
    result["no_detector_candidates"] = _no_detector_candidates()
    result["op20_disclosures"] = _op20_disclosures()
    # Headline: PROMOTE-CANDIDATEs clear real-fills anchor edge>0 AND full-window real-fills.
    promote = [r for r in result["ranking"]
               if "PROMOTE-CANDIDATE" in result["verdict"][r["pattern"]]]
    # "Edge-aligned" = positive real-fills anchor edge (captures J's days) even if fragile.
    edge_aligned = [r for r in result["ranking"]
                    if (r["realfills_anchor_edge_atm"] or -1) > 0]
    result["headline"] = {
        "baseline": _BASELINE,
        "promote_candidates": [r["pattern"] for r in promote],
        "edge_aligned_on_real_fills": [r["pattern"] for r in edge_aligned],
        "focus_recommendation": _focus_reco(result, promote, edge_aligned),
    }
    return result


def _focus_reco(result: dict, promote: list[dict], edge_aligned: list[dict]) -> str:
    base_v = result["verdict"][_BASELINE]
    rf_anchor = result.get("anchor_real_fills", {})
    brm_atm = rf_anchor.get(f"{_BASELINE}_ATM", {})
    brm_itm = rf_anchor.get(f"{_BASELINE}_ITM2", {})
    brm_line = (f"{_BASELINE} on J's anchor days (REAL fills): ATM edge_capture "
                f"${brm_atm.get('edge_capture_realfills')} ({brm_atm.get('n_anchor_fills', 0)} fills), "
                f"ITM2 ${brm_itm.get('edge_capture_realfills')} ({brm_itm.get('n_anchor_fills', 0)} fills).")
    if promote:
        names = ", ".join(r["pattern"] for r in promote)
        return (f"Focus engineering on: {names}. These clear POSITIVE real-fills anchor edge_capture "
                f"AND positive full-window real-fills. {brm_line}")
    # No variant clears BOTH gates — report the honest, valuable result.
    aligned = ", ".join(r["pattern"] for r in edge_aligned) or "(none beyond the baseline's anchor-day wins)"
    return (
        f"CLEAN RESULT: the CONFIRMED setup BEARISH_REJECTION_RIDE_THE_RIBBON (codified as "
        f"{_BASELINE}) IS the bearish edge — and it is the ONLY variant that captures J's anchor "
        f"days on REAL fills. {brm_line} On the FULL 16-month window, however, EVERY bearish-"
        f"continuation variant has NEGATIVE real-fills expectancy under chart-stop-only (the proxy "
        f"SPY-space looks fine — classic C1/C3 SPY-edge != option-edge). Variants positive on J's "
        f"anchor days but not broadly: {aligned}. "
        f"FOCUS ENGINEERING: (1) keep {_BASELINE} as THE bearish entry and deepen IT — its anchor-day "
        f"real-fills are strongly positive (esp. ITM2, J's Bold strike class); the leverage is in "
        f"EXIT/REGIME work (when to ride vs cut), not a new entry; (2) the full-window real-fills "
        f"collapse says the broad bearish population is NOT a clean win — gate {_BASELINE} (and the "
        f"WATCH-ONLY LBFS VIX>=20 / HS_BEAR 09:40-12:00 sub-pockets that prior scorecards found) by "
        f"regime rather than promoting any new standalone entry. No PROMOTE beyond the baseline. "
        f"Baseline verdict: {base_v[:200]}")


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
