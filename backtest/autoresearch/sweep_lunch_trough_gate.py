"""Lunch-trough time-of-day gate A/B — does excluding the documented midday volatility
trough (~12:00-13:30 ET) improve real-fills expectancy on the BEARISH_REJECTION setup?

THE FINDING UNDER TEST (docs/WEEKEND-RESEARCH-GAMEPLANS-2026-06-19.md, GP1 microstructure):
Intraday SPY volatility is U-shaped — high at open, trough at lunch, rising into the close.
The lunch lull is genuinely thinner/choppier. Hypothesis: gating out entries whose SIGNAL
BAR falls in the lunch trough avoids low-conviction chop and improves real-fills expectancy.
We already run an 11:30-12:00 no-trade window from a prior ratification; this tests whether
EXTENDING the exclusion to the documented ~12:00-13:30 trough helps FURTHER.

WHAT THIS DOES (lean, reuses the validate_bearish_continuation_family harness):
  * Replays the bearish-continuation family over the full real-fills window via the SAME
    BarContext pipeline + simulate_trade_real (chart-stop only, ATM + ITM2) as the family
    validator — so numbers are directly comparable to bearish-continuation-family.json.
  * For EVERY real fill it records the SIGNAL-BAR time (entry_time_et, naive ET) so we can
    bucket fills by time-of-day and A/B lunch-window exclusions.
  * BASELINE = current gates (no extra lunch exclusion).
    VARIANTS  = drop any fill whose signal bar is inside a candidate lunch window:
        {11:30-13:00, 12:00-13:30, 11:30-13:30}.
  * Per variant + baseline, per strike (ATM/ITM2): n, WR, expectancy, total, edge_capture
    (OP-16 anchor real-fills), and DSR (deflated Sharpe, n_trials = #variants tested).
  * Cross-check: prints which anchor-day winners (4/29 10:25, 5/01 13:09, 5/04 10:27) each
    window would remove — the no-regression guard. 5/01 @ 13:09 sits inside ALL three
    windows; 4/29 + 5/04 are morning and untouched.

HONEST-RESULT NOTE: the CONFIRMED setup is BEARISH_REJECTION_RIDE_THE_RIBBON, codified as
the morning watcher bearish_rejection_morning_watcher (fires 09:35-10:55 ONLY). That watcher
STRUCTURALLY cannot fire in any lunch window, so a lunch gate on it is a guaranteed no-op
(reported explicitly). The lunch-window test only has teeth on the WIDER bearish family
(BEARISH_REVERSAL_AT_LEVEL 11:00-14:30, LBFS, HS_BEAR) whose signals do land midday. We
report BOTH: (a) the confirmed-setup verdict (no-op, by construction) and (b) the wider
bearish-family verdict (where a lunch fill actually exists).

OP-20 disclosure: real-fills (simulate_trade_real over OPRA, chart-stop-only per L51/L55)
is the WR/expectancy authority. Levels are historically-rebuilt ★★ proxies (no look-ahead;
ctx.prior_bars only). SPY-space grade is not used for the verdict here. DSR n_obs is small
(few midday fills) -> low_power flagged; treat DSR as directional, not a hard gate (the
anchor-no-regression + expectancy delta is the real read).

Usage:
  python -m autoresearch.sweep_lunch_trough_gate --realfills \
      --out ../analysis/recommendations/lunch-trough-gate.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

# Reuse the bearish-continuation family harness (which itself reuses the breakout-family
# bootstrap, data loader, BarContext pipeline, _grade, _stats, ANCHORS, simulate_trade_real).
from autoresearch import validate_bearish_continuation_family as bcf  # noqa: E402
from autoresearch import validate_breakout_family as vbf  # noqa: E402

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
from lib.validation.deflated_sharpe import deflated_sharpe_ratio, MIN_RELIABLE_OBS  # noqa: E402

ANCHORS = bcf.ANCHORS  # {date: "WIN"|"LOSS"}
_BASELINE_WATCHER = bcf._BASELINE  # "BEARISH_REJECTION_MORNING" (the CONFIRMED setup)

# Candidate lunch-trough windows (signal-bar time inside [lo, hi) is excluded by the variant).
_LUNCH_WINDOWS = {
    "exclude_1130_1300": (dt.time(11, 30), dt.time(13, 0)),
    "exclude_1200_1330": (dt.time(12, 0), dt.time(13, 30)),
    "exclude_1130_1330": (dt.time(11, 30), dt.time(13, 30)),
}

# Anchor entry times (source-of-truth, from journal/trades.csv). Used for the no-regression
# cross-check: which anchor winners would each lunch window remove.
_ANCHOR_ENTRY_TIMES = {
    "2026-04-29": (dt.time(10, 25), "WIN", "710P +342 (morning)"),
    "2026-05-01": (dt.time(13, 9), "WIN", "721P +470 (MIDDAY 13:09)"),
    "2026-05-04": (dt.time(10, 27), "WIN", "721P +730 (morning)"),
}


def _in_window(t: dt.time, lo: dt.time, hi: dt.time) -> bool:
    return lo <= t < hi


def _collect_fills(start: dt.date, end: dt.date) -> list[dict]:
    """Replay the bearish-continuation family; return one row per REAL fill with its
    signal-bar time, stream, strike label, date and dollar P&L.

    Mirrors bcf.run's pipeline exactly (same data, same ctx construction, same detector
    set, same simulate_trade_real call) but emits per-fill rows tagged with entry_time_et
    so we can bucket by time-of-day. Real-fills only (chart-stop, ATM + ITM2).
    """
    from lib.simulator_real import simulate_trade_real

    spy_full, vix_full = vbf._load_data(start, end)
    spy_full["timestamp_et"] = vbf.pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
                   (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    ribbon_df = compute_ribbon(rth["close"])
    vix_aligned = _align_vix_to_spy(rth, vix_full)
    htf_stacks = _precompute_htf_15m_stacks(rth)

    bcf._reset_state()

    # 1) Detect: gather (idx, bar, sig, stream) for every fire (skip the dead control).
    fires: list[tuple] = []
    level_states: dict = {}
    ribbon_history: list = []
    last_date = None
    _lvl_cache = [None]
    _lvl_date = [None]

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
        for stream, detector in bcf._DETECTORS.items():
            if stream == bcf._DEAD_CONTROL:
                continue
            try:
                sig = detector(ctx)
            except Exception as _e:
                sys.stderr.write(f"{stream} bar={bar_time}: {type(_e).__name__}: {_e}\n")
                sig = None
            if sig is None:
                continue
            fires.append((idx, bar, sig, stream))

    # 2) Real-fills: simulate every fire (ANCHOR-INCLUSIVE cap mirrors bcf — but here we
    # want ALL midday fills, so cap per-stream at 200 yet always keep anchor-day fills).
    rows: list[dict] = []
    anchor_dates_iso = {d.isoformat() for d in ANCHORS}
    by_stream: dict[str, list] = defaultdict(list)
    for f in fires:
        by_stream[f[3]].append(f)
    for stream, sfires in by_stream.items():
        capped = list(sfires[:200])
        capped_idx = {c[0] for c in capped}
        for tup in sfires[200:]:
            _idx, _bar, _sig, _st = tup
            if str(_bar["timestamp_et"].date()) in anchor_dates_iso and _idx not in capped_idx:
                capped.append(tup)
                capped_idx.add(_idx)
        for label, offset in bcf._OFFSETS:  # ("ATM",0), ("ITM2",-2)
            for (idx, bar, sig, st) in capped:
                rej = (sig.metadata.get("rejection_level")
                       or sig.metadata.get("break_level")
                       or sig.metadata.get("neckline")
                       or sig.metadata.get("broken_level")
                       or sig.metadata.get("swept_level")
                       or sig.stop_price)
                ts = bar["timestamp_et"]
                try:
                    fill = simulate_trade_real(
                        entry_bar_idx=idx, entry_bar=bar, spy_df=rth, ribbon_df=ribbon_df,
                        rejection_level=float(rej), triggers_fired=sig.triggers_fired,
                        side="P", qty=3, setup=sig.setup_name,
                        premium_stop_pct=-0.99, strike_offset=offset)
                except Exception:
                    fill = None
                if fill is not None and getattr(fill, "dollar_pnl", None) is not None:
                    rows.append({
                        "stream": st,
                        "strike": label,
                        "date": str(ts.date()),
                        "time": ts.time(),
                        "pnl": float(fill.dollar_pnl),
                    })
    return rows


def _stats_with_edge(rows: list[dict]) -> dict:
    """n / WR / total / expectancy + OP-16 anchor real-fills edge_capture + DSR-ready returns."""
    base = vbf._stats([{"pnl": r["pnl"]} for r in rows])  # n, wr, total, exp
    # Anchor edge_capture: WIN-day P&L minus losses-incurred on LOSS days (real fills).
    win_pnl = 0.0
    loss_loss = 0.0
    n_anchor = 0
    for r in rows:
        lab = ANCHORS.get(dt.date.fromisoformat(r["date"]))
        if lab is None:
            continue
        n_anchor += 1
        if lab == "WIN":
            win_pnl += r["pnl"]
        elif lab == "LOSS":
            loss_loss += max(0.0, -r["pnl"])
    base["edge_capture"] = round(win_pnl - loss_loss, 2)
    base["n_anchor_fills"] = n_anchor
    return base


def _dsr_for(rows: list[dict], n_trials: int) -> dict:
    """Deflated Sharpe over the per-fill P&L series (deflated for n_trials variants tested)."""
    pnls = [r["pnl"] for r in rows]
    if len(pnls) < 2:
        return {"dsr": None, "sharpe": None, "n_obs": len(pnls), "low_power": True,
                "note": "n_obs<2 — DSR undefined"}
    try:
        res = deflated_sharpe_ratio(pnls, n_trials=n_trials)
    except ValueError as e:
        return {"dsr": None, "sharpe": None, "n_obs": len(pnls), "low_power": True,
                "note": f"DSR error: {e}"}
    return {"dsr": round(res.dsr, 4), "sharpe": round(res.sharpe, 4),
            "n_obs": res.n_obs, "n_trials": res.n_trials,
            "low_power": res.low_power,
            "note": ("low_power: n_obs<%d (Bailey-LdP asymptotic; treat as directional)" % MIN_RELIABLE_OBS)
                    if res.low_power else "ok"}


def _filtered(rows: list[dict], window: tuple | None) -> list[dict]:
    """Rows EXCLUDING any whose signal-bar time is inside [lo, hi). window=None -> baseline."""
    if window is None:
        return list(rows)
    lo, hi = window
    return [r for r in rows if not _in_window(r["time"], lo, hi)]


def _anchor_removal_check() -> dict:
    """Which anchor winners each candidate window would remove (no-regression guard)."""
    out = {}
    for wname, (lo, hi) in _LUNCH_WINDOWS.items():
        removed = []
        for d, (t, lab, desc) in _ANCHOR_ENTRY_TIMES.items():
            if _in_window(t, lo, hi):
                removed.append({"date": d, "entry_time": t.strftime("%H:%M"), "label": lab, "desc": desc})
        out[wname] = {
            "window": f"{lo.strftime('%H:%M')}-{hi.strftime('%H:%M')}",
            "anchor_winners_removed": removed,
            "removes_a_winner": any(r["label"] == "WIN" for r in removed),
        }
    return out


def _build(rows: list[dict], start: dt.date, end: dt.date) -> dict:
    n_trials = len(_LUNCH_WINDOWS) + 1  # baseline + variants searched
    confirmed = [r for r in rows if r["stream"] == _BASELINE_WATCHER]
    wider = rows  # whole bearish-continuation family (incl. midday watchers)

    def _scope_block(pool: list[dict], scope_name: str) -> dict:
        blk = {}
        for strike in ("ATM", "ITM2"):
            srows = [r for r in pool if r["strike"] == strike]
            variants = {}
            base_rows = _filtered(srows, None)
            base_stats = _stats_with_edge(base_rows)
            base_dsr = _dsr_for(base_rows, n_trials)
            variants["baseline"] = {**base_stats, "dsr": base_dsr,
                                    "window": "none (current gates)"}
            for wname, win in _LUNCH_WINDOWS.items():
                vrows = _filtered(srows, win)
                vstats = _stats_with_edge(vrows)
                vdsr = _dsr_for(vrows, n_trials)
                # Deltas vs baseline (positive exp delta = improvement).
                variants[wname] = {
                    **vstats, "dsr": vdsr,
                    "window": f"{win[0].strftime('%H:%M')}-{win[1].strftime('%H:%M')}",
                    "n_excluded": base_stats["n"] - vstats["n"],
                    "exp_delta_vs_baseline": round(vstats["exp"] - base_stats["exp"], 2),
                    "total_delta_vs_baseline": round(vstats["total"] - base_stats["total"], 2),
                    "wr_delta_vs_baseline": round(vstats["wr"] - base_stats["wr"], 1),
                    "edge_capture_delta_vs_baseline": round(
                        vstats["edge_capture"] - base_stats["edge_capture"], 2),
                }
            blk[strike] = variants
        return blk

    # Time-of-day histogram of all fills (sanity: where do bearish fills cluster?).
    tod = defaultdict(lambda: {"n": 0, "pnl": 0.0})
    for r in rows:
        if r["strike"] != "ATM":
            continue
        hh = r["time"].hour
        slot = f"{hh:02d}:00-{hh:02d}:59"
        tod[slot]["n"] += 1
        tod[slot]["pnl"] += r["pnl"]
    tod_sorted = {k: {"n": v["n"], "total_pnl": round(v["pnl"], 2)} for k, v in sorted(tod.items())}

    # Count midday fills (the only place a lunch gate can bite) per window.
    midday_counts = {}
    for wname, win in _LUNCH_WINDOWS.items():
        n_conf = len([r for r in confirmed if r["strike"] == "ATM" and _in_window(r["time"], *win)])
        n_wide = len([r for r in wider if r["strike"] == "ATM" and _in_window(r["time"], *win)])
        midday_counts[wname] = {"confirmed_setup_fills_in_window": n_conf,
                                "wider_family_fills_in_window": n_wide}

    result = {
        "window": f"{start}..{end}",
        "test": "lunch_trough_time_of_day_gate",
        "setup_under_test": "BEARISH_REJECTION (confirmed = morning watcher; wider = full bearish family)",
        "candidate_windows": {k: f"{v[0].strftime('%H:%M')}-{v[1].strftime('%H:%M')}"
                              for k, v in _LUNCH_WINDOWS.items()},
        "n_trials_for_dsr": n_trials,
        "confirmed_setup": _scope_block(confirmed, "confirmed"),
        "wider_bearish_family": _scope_block(wider, "wider"),
        "fills_in_lunch_window": midday_counts,
        "time_of_day_histogram_atm": tod_sorted,
        "anchor_no_regression": _anchor_removal_check(),
    }
    result["verdict"] = _verdict(result, confirmed, wider)
    result["op20_disclosures"] = {
        "authority": "real-fills (simulate_trade_real, chart-stop only premium_stop_pct=-0.99, "
                     "ATM+ITM2 puts) is the WR/expectancy authority (L51/L55, C1/C3).",
        "levels": "historically-rebuilt ★★ proxies (_detect_from_history as-of each day); "
                  "no look-ahead (ctx.prior_bars only). NOT production ★★★ named set (OP-20).",
        "dsr": "deflated for n_trials=%d (baseline + 3 lunch windows). n_obs of midday fills is "
               "small -> low_power; DSR is directional, not the gate. The gate is exp delta + "
               "anchor-no-regression." % n_trials,
        "confirmed_vs_wider": "The CONFIRMED setup is the morning watcher (09:35-10:55) which "
                              "cannot fire midday -> a lunch gate on it is a structural no-op. "
                              "The wider family (BEARISH_REVERSAL 11:00-14:30 / LBFS / HS) is the "
                              "only scope where a lunch fill exists; that is where the A/B has teeth.",
    }
    return result


def _verdict(result: dict, confirmed: list[dict], wider: list[dict]) -> dict:
    """PROPOSE / NO-WIN verdict. A lunch gate is worth proposing only if, on the scope where
    it actually changes fills, it IMPROVES expectancy (and edge_capture) WITHOUT removing an
    anchor winner. Otherwise it's a useless (or harmful) gate -> do not add it."""
    # No-op detection on confirmed setup.
    conf_in_lunch = {w: len([r for r in confirmed if r["strike"] == "ATM" and _in_window(r["time"], *win)])
                     for w, win in _LUNCH_WINDOWS.items()}
    confirmed_noop = all(v == 0 for v in conf_in_lunch.values())

    lines = []
    proposable = []
    for scope_name, block in (("confirmed_setup", result["confirmed_setup"]),
                              ("wider_bearish_family", result["wider_bearish_family"])):
        for strike in ("ATM", "ITM2"):
            base = block[strike]["baseline"]
            for wname in _LUNCH_WINDOWS:
                v = block[strike][wname]
                removes_winner = result["anchor_no_regression"][wname]["removes_a_winner"]
                if v["n_excluded"] == 0:
                    continue  # gate changed nothing in this scope/strike — skip
                improved = (v["exp_delta_vs_baseline"] > 0
                            and v["edge_capture_delta_vs_baseline"] >= 0
                            and not removes_winner)
                tag = "IMPROVES" if improved else (
                    "REMOVES-WINNER" if removes_winner else "NO-IMPROVE/HURTS")
                lines.append(
                    f"[{scope_name}/{strike}/{wname}] excluded {v['n_excluded']} fills: "
                    f"exp {base['exp']}->{v['exp']} (d {v['exp_delta_vs_baseline']:+}), "
                    f"WR {base['wr']}->{v['wr']}, edge_cap d {v['edge_capture_delta_vs_baseline']:+}, "
                    f"removes_winner={removes_winner} => {tag}")
                if improved:
                    proposable.append(f"{scope_name}/{strike}/{wname}")

    if confirmed_noop:
        conf_summary = ("CONFIRMED-SETUP NO-OP: the morning watcher (09:35-10:55) fired 0 times in "
                        "every candidate lunch window — a lunch-trough gate on BEARISH_REJECTION "
                        "(the confirmed setup) changes NOTHING. Current time-gating already excludes "
                        "the lunch trough by construction.")
    else:
        conf_summary = ("CONFIRMED setup had midday fills: %s." % conf_in_lunch)

    if proposable:
        headline = ("PROPOSE (narrow): a lunch-trough exclusion improves real-fills expectancy AND "
                    "edge_capture without removing an anchor winner in: " + ", ".join(proposable) +
                    ". " + conf_summary)
        recommendation = "PROPOSE"
    else:
        headline = ("NO-WIN — do NOT add a lunch-trough gate. On the only scope where it changes "
                    "fills (the wider bearish family), excluding the lunch window does not improve "
                    "real-fills expectancy/edge_capture (and/or removes the 5/01 13:09 anchor "
                    "winner). " + conf_summary + " The current 09:35 morning gate + existing "
                    "11:30-12:00 window already place entries on the right shoulder; extending the "
                    "lunch exclusion adds a useless (or edge-cutting) constraint.")
        recommendation = "NO-WIN / DO-NOT-PROPOSE"

    return {"recommendation": recommendation, "headline": headline,
            "confirmed_setup_noop": confirmed_noop,
            "confirmed_fills_in_lunch_by_window": conf_in_lunch,
            "detail": lines}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2026-06-16")
    ap.add_argument("--realfills", action="store_true", default=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    start, end = dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end)
    rows = _collect_fills(start, end)
    sys.stderr.write(f"[collect] {len(rows)} real fills across bearish-continuation family "
                     f"(ATM+ITM2) over {start}..{end}\n")
    result = _build(rows, start, end)
    txt = json.dumps(result, indent=2, default=str)
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
