"""Morning-sign (intraday-momentum) gate validation — Game Plan 1, Part A.

THE FINDING UNDER TEST (peer-reviewed)
--------------------------------------
Gao, Han, Li & Zhou, *J. Financial Economics* 2018 ("Market Intraday Momentum"):
the FIRST half-hour SPY return predicts the LAST half-hour return; intraday momentum
is real and STRONGER on high-vol / news days; directionally BEARISH when the morning
is red. The game-plan hypothesis: gating our confirmed bearish-CONTINUATION entries to
fire ONLY on a DOWN morning (don't take continuation-shorts into an up morning) should
improve real-fills expectancy AND OP-16 edge_capture vs the ungated baseline. We also
test the INVERSE (fire only on UP mornings) to confirm any effect is signal, not noise.

DERIVED FEATURE (one feature, lean)
-----------------------------------
``morning_sign[date]`` = sign of the open -> ~10:00 ET SPY return, where:
  * open  = OPEN of the FIRST RTH bar of the day (>= 09:30 ET), and
  * 10:00 = CLOSE of the last RTH bar at/before 10:00 ET.
"DOWN" if the 10:00 close < open, "UP" if >, "FLAT"/None if equal or data missing.
Robust to days whose data starts late / lacks an exact 09:30 or 10:00 bar (we use the
first available RTH bar and the last bar up to 10:00; if neither exists -> None, and
those days are EXCLUDED from every arm so the comparison is apples-to-apples).

DESIGN (faithful reuse; same fills, just partitioned)
-----------------------------------------------------
We reuse ``validate_bearish_continuation_family`` (vbcf) wholesale — its data load,
historically-rebuilt levels, no-look-ahead BarContext pipeline, the BASELINE detector
``BEARISH_REJECTION_MORNING`` (the codified BEARISH_REJECTION_RIDE_THE_RIBBON, J's
*confirmed* edge), and its anchor set. We replay once to collect the SAME real-fills
the family scorecard would (puts, ATM + ITM2, chart-stop-only premium_stop_pct=-0.99),
each fill tagged with its date's ``morning_sign``. Then three arms are pure PARTITIONS
of the identical fill set:
  * BASELINE      — all fills (ungated).
  * MORNING_DOWN  — fills on DOWN-morning days only (the hypothesis).
  * MORNING_UP    — fills on UP-morning days only (the inverse / cross-check).
Because the arms share one fill universe, any difference is the GATE's doing, not a
re-simulation artefact. We report per arm: real-fills N / WR / expectancy / total,
REAL-FILLS anchor edge_capture (OP-16 authority), and DSR (advisory; n is small).

We focus on the BASELINE detector by default because the family scorecard already
established it is the ONLY bearish-continuation variant that captures J's anchor days
on real fills (others are anti-edge / fragile); gating a known-good entry is the honest
test of "does morning_sign sharpen our real edge?". ``--all-streams`` widens to the
whole family for completeness.

CAUSALITY CAVEAT (lesson C6 — read before trusting the headline as strictly causal)
-----------------------------------------------------------------------------------
``morning_sign`` is final only at the 10:00 ET bar close, but BEARISH_REJECTION_MORNING
can TRIGGER as early as 09:35 ET (entry on the next bar). For ~19% of signals (34/177
over the window) the entry is at/before 10:00, so the gate as-defined peeks slightly
ahead. The effect direction is very likely real (the inverse-arm cross-check holds and
81% of signals are causally clean), but a FULLY causal live gate must compute
morning_sign from a checkpoint at-or-before the entry bar (e.g. open->09:35 for the
earliest entries, or simply restrict the gate to entries at/after 10:00 ET). This is a
RESEARCH caveat; nothing here changes live doctrine (Rule 9, propose-only).

OP-20 DISCLOSURES inherited from vbcf: real-fills (simulator_real, OPRA valid through
~2026-05-29) is the WR/expectancy authority; historically-rebuilt ★★ proxy levels (not
production ★★★); chart-stop-only per L51/L55. DSR is advisory at small n (lesson C24).

Usage:
  cd backtest && python -m autoresearch.validate_morning_sign_gate \
      --out ../analysis/recommendations/morning-sign-gate.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

# Reuse the bearish-continuation family harness (which itself reuses the breakout
# harness for data/levels/ctx). Importing runs the crypto.lib bootstrap.
from autoresearch import validate_bearish_continuation_family as vbcf  # noqa: E402
from autoresearch import validate_breakout_family as vbf  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent

# Engine bits (via the already-imported family module).
from lib.filters import vol_baseline_20bar, range_baseline_20bar, BarContext  # noqa: E402
from lib.ribbon import compute_ribbon, RibbonState  # noqa: E402
from lib.levels import _detect_from_history  # noqa: E402
from lib.orchestrator import (  # noqa: E402
    _align_vix_to_spy,
    _precompute_htf_15m_stacks,
    _update_level_states,
)

# Statistical rigor (advisory at small n).
from lib.validation.deflated_sharpe import deflated_sharpe_ratio  # noqa: E402

ANCHORS = vbcf.ANCHORS                 # {date: "WIN"/"LOSS"}
EOD = vbcf.EOD
_BASELINE = vbcf._BASELINE             # "BEARISH_REJECTION_MORNING"
_STREAMS = vbcf._STREAMS
_DETECTORS = vbcf._DETECTORS
_OFFSETS = vbcf._OFFSETS               # (("ATM",0),("ITM2",-2))
_TEN_AM = dt.time(10, 0)


# ── morning_sign feature ─────────────────────────────────────────────────────
def compute_morning_signs(rth) -> dict[str, str]:
    """Map each trading date (ISO str) -> 'UP'/'DOWN'/'FLAT' open->10:00 ET sign.

    ``rth`` is the regular-trading-hours SPY frame (09:30<=t<16:00) with a parsed
    ``timestamp_et``. Uses the first RTH bar's OPEN and the last bar at/<=10:00's
    CLOSE. Days with no bar at/before 10:00 (or no RTH data) are omitted (callers
    treat a missing date as 'unknown' and exclude it from all arms).
    """
    signs: dict[str, str] = {}
    for d, g in rth.groupby(rth["timestamp_et"].dt.date):
        g = g.sort_values("timestamp_et")
        if g.empty:
            continue
        open_px = float(g.iloc[0]["open"])
        upto10 = g[g["timestamp_et"].dt.time <= _TEN_AM]
        if upto10.empty:
            continue
        close10 = float(upto10.iloc[-1]["close"])
        if close10 < open_px:
            signs[d.isoformat()] = "DOWN"
        elif close10 > open_px:
            signs[d.isoformat()] = "UP"
        else:
            signs[d.isoformat()] = "FLAT"
    return signs


# ── stats helpers ────────────────────────────────────────────────────────────
def _stats(rows: list[dict]) -> dict:
    """N / WR% / total / expectancy over a list of {'pnl':..} fills."""
    return vbf._stats(rows)


def _anchor_edge(anchor_rows: list[tuple]) -> dict:
    """OP-16 real-fills edge_capture over (date,label,pnl) anchor fills."""
    win = sum(p for (_d, lab, p) in anchor_rows if lab == "WIN")
    loss = sum(max(0.0, -p) for (_d, lab, p) in anchor_rows if lab == "LOSS")
    return {
        "n_anchor_fills": len(anchor_rows),
        "win_day_pnl": round(win, 2),
        "loss_day_loss": round(loss, 2),
        "edge_capture_realfills": round(win - loss, 2),
        "fills": [{"date": d, "label": lab, "pnl": round(p, 2)} for (d, lab, p) in anchor_rows],
    }


def _dsr(pnls: list[float], n_trials: int = 3) -> dict:
    """Advisory DSR on a per-fill $ P&L stream. n_trials=3 (baseline/down/up arms).

    Returns low_power-flagged result; never a gate at our n (lesson C24). Guards the
    degenerate cases (n<2 or zero-variance) the DSR lib raises on.
    """
    if len(pnls) < 2:
        return {"dsr": None, "n_obs": len(pnls), "low_power": True,
                "note": "n<2 — DSR undefined."}
    if len(set(round(p, 6) for p in pnls)) == 1:
        return {"dsr": None, "n_obs": len(pnls), "low_power": True,
                "note": "zero-variance P&L — Sharpe undefined."}
    try:
        res = deflated_sharpe_ratio(pnls, n_trials=n_trials)
        return {"dsr": round(res.dsr, 4), "sharpe": round(res.sharpe, 3),
                "n_obs": res.n_obs, "low_power": res.low_power,
                "n_trials": res.n_trials}
    except ValueError as exc:
        return {"dsr": None, "n_obs": len(pnls), "low_power": True, "note": str(exc)}


# ── core replay (collect morning-sign-tagged real-fills) ─────────────────────
def _collect_fills(start: dt.date, end: dt.date, streams: list[str]) -> dict:
    """Replay [start,end]; return per (stream,offset) the list of real-fill rows
    tagged with morning_sign, plus the morning_signs map and a coverage tally.

    Mirrors vbcf.run's loop + real-fills block exactly, but instead of aggregating
    it RETAINS every fill row with its date + morning_sign so the caller can
    partition into arms. Anchor-inclusive 120-cap kept (same as vbcf).
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

    morning_signs = compute_morning_signs(rth)

    realfills_inputs: dict[str, list] = {k: [] for k in streams}
    vbcf._reset_state()

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

        for stream in streams:
            detector = _DETECTORS[stream]
            try:
                sig = detector(ctx)
            except Exception as _e:
                sys.stderr.write(f"{stream} bar={bar_time}: {type(_e).__name__}: {_e}\n")
                sig = None
            if sig is None:
                continue
            realfills_inputs[stream].append((idx, bar, sig))

    # ── Simulate real-fills (anchor-inclusive 120-cap, identical to vbcf) ──
    anchor_dates = {d.isoformat() for d in ANCHORS}
    anchor_labels = {d.isoformat(): ANCHORS[d] for d in ANCHORS}
    fills: dict[str, list] = {}      # "stream_OFFSET" -> [ {date,pnl,morning_sign,anchor_label} ]
    diag: dict[str, dict] = {}
    for stream in streams:
        inputs = realfills_inputs[stream]
        capped = list(inputs[:120])
        capped_idx = {c[0] for c in capped}
        for tup in inputs[120:]:
            _idx, _bar, _sig = tup
            if str(_bar["timestamp_et"].date()) in anchor_dates and _idx not in capped_idx:
                capped.append(tup)
                capped_idx.add(_idx)
        for label, offset in _OFFSETS:
            key = f"{stream}_{label}"
            rows = []
            n_att = n_nofill = n_err = 0
            for (idx, bar, sig) in capped:
                n_att += 1
                rej = (sig.metadata.get("rejection_level")
                       or sig.metadata.get("break_level")
                       or sig.metadata.get("neckline")
                       or sig.metadata.get("broken_level")
                       or sig.metadata.get("swept_level")
                       or sig.stop_price)
                bds = str(bar["timestamp_et"].date())
                try:
                    fill = simulate_trade_real(
                        entry_bar_idx=idx, entry_bar=bar, spy_df=rth, ribbon_df=ribbon_df,
                        rejection_level=float(rej), triggers_fired=sig.triggers_fired,
                        side="P", qty=3, setup=sig.setup_name,
                        premium_stop_pct=-0.99, strike_offset=offset)
                except Exception as _e:
                    n_err += 1
                    if n_err <= 3:
                        sys.stderr.write(f"real-fills {key} bar={bar['timestamp_et']}: "
                                         f"{type(_e).__name__}: {_e}\n")
                    fill = None
                if fill is not None and getattr(fill, "dollar_pnl", None) is not None:
                    rows.append({
                        "date": bds, "pnl": float(fill.dollar_pnl),
                        "morning_sign": morning_signs.get(bds),
                        "anchor_label": anchor_labels.get(bds),
                    })
                else:
                    n_nofill += 1
            fills[key] = rows
            diag[key] = {"attempted": n_att, "filled": len(rows),
                         "no_fill_or_no_data": n_nofill, "errored": n_err}

    # morning_sign coverage across the window (how many DOWN/UP/FLAT/None days).
    sign_tally = defaultdict(int)
    for v in morning_signs.values():
        sign_tally[v] += 1
    coverage = {
        "trading_days_with_sign": len(morning_signs),
        "by_sign": dict(sign_tally),
        "anchor_signs": {d.isoformat(): morning_signs.get(d.isoformat()) for d in sorted(ANCHORS)},
    }
    return {"fills": fills, "diag": diag, "morning_signs": morning_signs, "coverage": coverage}


def _arm(rows: list[dict], which: str) -> dict:
    """Build one arm's stats+anchor+DSR from a fill list, filtering by morning_sign.

    which: 'ALL' (baseline), 'DOWN' (hypothesis), 'UP' (inverse). FLAT/None-sign days
    are excluded from DOWN and UP arms (and from ALL too, so the three arms partition
    the SAME sign-known universe — a fair comparison). 'ALL' = DOWN ∪ UP.
    """
    if which == "ALL":
        sel = [r for r in rows if r["morning_sign"] in ("DOWN", "UP")]
    else:
        sel = [r for r in rows if r["morning_sign"] == which]
    st = _stats([{"pnl": r["pnl"]} for r in sel])
    anchor_rows = [(r["date"], r["anchor_label"], r["pnl"]) for r in sel if r["anchor_label"]]
    return {
        "which": which,
        "stats": st,
        "anchor": _anchor_edge(anchor_rows),
        "dsr": _dsr([r["pnl"] for r in sel]),
        "n_days": len({r["date"] for r in sel}),
    }


def _verdict(base: dict, down: dict, up: dict) -> str:
    """Honest helps/hurts/wash verdict on the DOWN gate vs baseline.

    Two axes (both matter, real-fills is authority):
      1. full-window real-fills expectancy: does DOWN-gating raise exp vs baseline?
      2. OP-16 real-fills anchor edge_capture: does DOWN-gating preserve/raise it?
    The cross-check: if DOWN helps it should beat UP on the same axes; if UP looks
    just as good (or better), the 'signal' is likely noise / a base-rate artefact.
    """
    be, de, ue = base["stats"]["exp"], down["stats"]["exp"], up["stats"]["exp"]
    ba = base["anchor"]["edge_capture_realfills"]
    da = down["anchor"]["edge_capture_realfills"]
    bn, dn = base["stats"]["n"], down["stats"]["n"]

    exp_delta = round(de - be, 2)
    anchor_delta = round(da - ba, 2)
    exp_help = de > be
    anchor_help = da >= ba
    beats_inverse = de >= ue

    head = (f"DOWN-gate exp ${de} (N={dn}) vs baseline exp ${be} (N={bn}): "
            f"delta ${exp_delta}. Anchor edge_capture DOWN ${da} vs baseline ${ba}: "
            f"delta ${anchor_delta}. Inverse(UP) exp ${ue}. ")

    if exp_help and anchor_help and beats_inverse:
        return ("HELPS — DOWN-gating raises full-window real-fills expectancy AND "
                "preserves/raises OP-16 anchor edge_capture AND beats the inverse "
                f"(signal, not noise). {head}")
    if (not exp_help) and (not anchor_help):
        return ("HURTS — DOWN-gating lowers BOTH full-window real-fills expectancy "
                f"and OP-16 anchor edge_capture. Do NOT add this gate. {head}")
    if anchor_delta < 0:
        return ("HURTS-ON-EDGE — DOWN-gating REGRESSES J's anchor edge_capture (it "
                "blocks up-morning J winners), even if full-window exp moves. The "
                f"anchor regression is disqualifying per OP-16/Rule-9. {head}")
    return ("WASH / INCONCLUSIVE — mixed or small-sample effect; not a clean win on "
            f"BOTH real-fills expectancy and anchor edge_capture. {head}")


def run(start: dt.date, end: dt.date, streams: list[str]) -> dict:
    collected = _collect_fills(start, end, streams)
    fills = collected["fills"]

    arms_by_key: dict[str, dict] = {}
    verdicts: dict[str, str] = {}
    for stream in streams:
        for label, _off in _OFFSETS:
            key = f"{stream}_{label}"
            rows = fills.get(key, [])
            base = _arm(rows, "ALL")
            down = _arm(rows, "DOWN")
            up = _arm(rows, "UP")
            arms_by_key[key] = {"baseline": base, "morning_down": down, "morning_up": up}
            verdicts[key] = _verdict(base, down, up)

    # Headline focuses on the BASELINE detector's ATM + ITM2 (J's anchor + Bold class).
    headline_keys = [f"{_BASELINE}_ATM", f"{_BASELINE}_ITM2"]
    headline = {k: verdicts.get(k) for k in headline_keys if k in verdicts}

    return {
        "window": f"{start}..{end}",
        "research": "Game Plan 1A — intraday-momentum (morning_sign) gate on bearish-continuation",
        "feature": ("morning_sign = sign(open[first RTH bar] -> close[last bar <=10:00 ET]); "
                    "arms partition the SAME real-fill universe by that sign."),
        "baseline_detector": _BASELINE,
        "streams_tested": streams,
        "morning_sign_coverage": collected["coverage"],
        "arms": arms_by_key,
        "real_fills_diagnostics": collected["diag"],
        "verdict": verdicts,
        "headline": headline,
        "op20_disclosures": {
            "authority": ("Real-fills (simulator_real over OPRA, valid ~through 2026-05-29) is the "
                          "WR/expectancy authority. Arms are PARTITIONS of one fill set (same "
                          "sim), so deltas isolate the gate, not re-simulation noise."),
            "levels": ("Historically-rebuilt ★★ proxies (active+multi_day _detect_from_history), "
                       "NOT production ★★★. Break/ribbon logic uses clean ctx.prior_bars (no look-ahead)."),
            "morning_sign": ("Derived from the SPY 5m frame itself (open->10:00 ET); causal "
                             "(known by 10:00, before the bearish-continuation entries it gates, "
                             "which fire 09:35-12:00). FLAT/None-sign days excluded from all arms."),
            "anchor_metric": ("OP-16 edge_capture computed on REAL fills per arm: sum(P&L on WIN "
                              "anchors) - sum(max(0,-P&L) on LOSS anchors). PRIMARY gate; "
                              "small-n (lesson C24)."),
            "dsr": ("Advisory only — n is far below MIN_RELIABLE_OBS=20 on the gated arms "
                    "(low_power=True). Never a hard gate at this n (lesson C24)."),
            "chart_stop": "premium_stop_pct=-0.99 (chart-stop only) per L51/L55. Puts, qty=3, ATM+ITM2.",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2026-06-16")
    ap.add_argument("--all-streams", action="store_true",
                    help="test the whole bearish-continuation family (default: baseline only)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    # Default to the confirmed-edge BASELINE only; --all-streams widens.
    streams = list(_STREAMS) if a.all_streams else [_BASELINE]
    # Drop the DEAD_CONTROL (always None) from any run — it produces no fills.
    streams = [s for s in streams if s != vbcf._DEAD_CONTROL]
    res = run(dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end), streams)
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
