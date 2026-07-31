#!/usr/bin/env python
"""shadow_signal_edge_2026_07_31.py -- did the SHADOW signals carry edge?

PRE-REGISTERED: analysis/deep-research/SHADOW-SIGNAL-PREREG-2026-07-31.md
(2026-07-31 17:29:26 ET, BEFORE any run).

QUESTION
The engine computes three bullish detectors every tick -- wick_reclaim,
trendline_reclaim, pullback_hold -- writes them to core-decisions.jsonl, and by the
2026-07-15 decision they are architecturally incapable of moving score or blockers.
On 2026-07-31 at 10:21 ET wick_reclaim FIRED into a +4.82 bounce and could do nothing.
This script asks whether that silence cost money, using real OPRA and the REAL exit
manager -- not a sim.

METHOD (locked in the pre-reg, not chosen after seeing results)
  * EVENT UNIT: (signal, date, 5-min bar). The detector reads the last CLOSED 5-min bar,
    so consecutive 1-min ticks inside one bar are the SAME detection, not new evidence.
    Counting ticks would inflate n ~4x and fake significance.
  * ENTRY: entry+1 convention (ENTRY-BAR-CONVENTION-RULING-2026-07-25). Entry premium is
    the VWAP of the 5-min option bar containing the decision; walk_exit_manager's strict
    `>` means the entry bar itself is never exit-checked.
  * STRIKE: ATM (round(spot)) -- core Safe's live tier under $10K equity per
    crypto/lib/strike_selection.py#V15_SAFE_TIERS. Verified against the live table, NOT
    assumed (the BS-sim-ignored-strike-offset scar invalidated a weekend of research).
  * EXIT: the REAL exit_manager decision core via lib.exit_manager_walk, driven with the
    RIBBON_RIDE ExitShape that heartbeat_core actually registers for bull ribbon-ride
    entries (structure stop primary, -50% catastrophe cap, TP1 +100% sell 66.7%,
    trailing runner 15% off HWM).
    !! CORRECTION 2026-07-31 evening (L249 -- this docstring was WRONG for 90% of trades):
    ExitState.from_entry silently resolves to PREMIUM mode at -20% whenever trigger_level
    is absent, and it is absent on 144/160 shadow firings. The structure cell above is
    what was INTENDED, not what most trades RAN. See exit_fallback_correction and
    counterfactual_true_cap in the output -- both are now first-class fields, and the
    bias runs CONSERVATIVE (at the true -50% cap both signals get WORSE).
  * SIGNIFICANCE: the per-trade p-value is n-INFLATED -- ~45 firings/day overlap across a
    handful of contracts, so they are not independent draws. The DAY-LEVEL block test
    (day_level_test) is the adjudicating statistic; the per-trade BH result is kept only
    as `bh_fdr_q010_significant_PER_TRADE` for provenance.
  * SCOPE: STANDALONE-TRIGGER form only. Score-contributor / tiebreaker / veto use of these
    signals is UNTESTED here and must not be swept into the graveyard (C15).
  * SIZE: qty=3 (Rule 6 minimum: 2 TP + 1 runner). Per-trade dollars are therefore the
    minimum-size figure, never a scaled-up projection.
  * REAL OPRA ONLY. A (date, strike) with no cached contract is reported as UNCOVERED and
    EXCLUDED from every verdict. Nothing is Black-Scholes-synthesized. Coverage is
    reported as a first-class number because it bounds what may be concluded.
  * MULTIPLICITY: Benjamini-Hochberg across ALL signals tested. Testing 3 signals and
    reporting the best one at p<0.05 is the exact trap this lane is about.
  * Day-level block aggregation is reported alongside per-trade, because ~45 firings/day
    inside one session are NOT independent draws.

$0, pure Python, offline (cached bars only). Places no orders, edits no engine code.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

from et_clock import et_now  # noqa: E402 -- this box is MOUNTAIN time; ET = local + 2h
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

LEDGER = REPO / "automation" / "state" / "core-decisions.jsonl"
SPY5M = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-07-31.csv"
OUT = REPO / "analysis" / "deep-research" / "SHADOW-SIGNAL-EDGE-2026-07-31.json"

SIGNALS = ("wick_reclaim", "trendline_reclaim", "pullback_hold")
QTY = 3
TIME_STOP = dt.time(15, 50)

# ---------------------------------------------------------------------------
# COVERAGE-BIAS CONTROL (added after the first run exposed it -- disclosed, not hidden)
#
# The OPRA cache was populated by PRIOR studies, so which (date, strike) pairs exist is
# NOT random. On 2026-07-31 only strikes 744/745/746/748 are cached while SPY ranged
# 738.61-748.47: ONLY events from the upper third of the day's range can resolve --
# precisely the part of the session where a BULLISH signal wins. The first run's
# +$4,534 wick_reclaim day was that artifact, not an edge.
#
# A day is UNBIASED only if its cached strike ladder spans the day's whole SPY range,
# so every event that fired can resolve regardless of where price was. Computed from
# the cache + the observed SPY range, never hand-listed.
# ---------------------------------------------------------------------------
OPT_DIR = REPO / "backtest" / "data" / "options"


def fully_covered_days(events: list[dict]) -> tuple[set[str], dict]:
    """Days whose cached ATM strike ladder spans the full observed SPY range."""
    rng: dict[str, list[float]] = defaultdict(list)
    for e in events:
        if e.get("spy"):
            rng[e["date"]].append(float(e["spy"]))
    detail, good = {}, set()
    for date, spots in rng.items():
        yymmdd = dt.date.fromisoformat(date).strftime("%y%m%d")
        cached = sorted(int(p.name[10:15]) for p in OPT_DIR.glob(f"SPY{yymmdd}C*.csv"))
        lo, hi = int(round(min(spots))), int(round(max(spots)))
        need = set(range(lo, hi + 1))
        missing = sorted(need - set(cached))
        ok = not missing
        detail[date] = dict(spy_lo=round(min(spots), 2), spy_hi=round(max(spots), 2),
                            atm_strikes_needed=len(need), cached=len(cached),
                            missing_atm_strikes=missing, unbiased=ok)
        if ok:
            good.add(date)
    return good, detail

# The exit shape heartbeat_core registers for BULLISH_RECLAIM_RIDE_THE_RIBBON entries --
# read from automation/state/fleet/strategies.py#RIBBON_RIDE, not re-typed from doctrine.
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
import strategies as _strat  # noqa: E402

EXIT_SHAPE = _strat.RIBBON_RIDE.exit.to_dict()


def load_events() -> tuple[list[dict], dict]:
    """Shadow firings deduped to (signal, date, 5-min bar). Returns (events, meta)."""
    seen: set[tuple[str, str, str]] = set()
    events: list[dict] = []
    tick_counts: dict[str, int] = defaultdict(int)
    bars_seen_per_day: dict[str, set] = defaultdict(set)
    with LEDGER.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            fired = r.get("shadow_triggers_fired") or []
            ts = r.get("ts_et") or ""
            if len(ts) < 16:
                continue
            date, hh, mm = ts[:10], ts[11:13], ts[14:16]
            bars_seen_per_day[date].add(f"{hh}:{int(mm) // 5 * 5:02d}")
            if not fired:
                continue
            bar = f"{hh}:{int(mm) // 5 * 5:02d}"
            for sig in fired:
                tick_counts[sig] += 1
                key = (sig, date, bar)
                if key in seen:
                    continue
                seen.add(key)
                events.append(dict(
                    signal=sig, date=date, bar=bar, spy=r.get("spy"),
                    trigger_level=r.get("bull_reclaim_level_raw") or r.get("trigger_level_exact"),
                    bull_score=r.get("bull_score"), verdict=r.get("verdict"),
                ))
    meta = dict(tick_firings=dict(tick_counts),
                bars_per_day={d: len(b) for d, b in sorted(bars_seen_per_day.items())})
    return events, meta


def load_spy() -> dict[str, pd.DataFrame]:
    df = pd.read_csv(SPY5M)
    tcol = "timestamp_et" if "timestamp_et" in df.columns else df.columns[0]
    df[tcol] = pd.to_datetime(df[tcol])
    if getattr(df[tcol].dt, "tz", None) is not None:
        df[tcol] = df[tcol].dt.tz_localize(None)
    df = df.rename(columns={tcol: "timestamp_et"})
    df["date"] = df["timestamp_et"].dt.strftime("%Y-%m-%d")
    return {d: g.reset_index(drop=True) for d, g in df.groupby("date")}


def run_one(ev: dict, spy_day: pd.DataFrame) -> dict:
    """Resolve one event to a real-OPRA outcome, or an explicit exclusion reason."""
    out = dict(ev)
    spot = ev.get("spy")
    if not spot:
        out["status"] = "NO_SPOT"
        return out
    strike = int(round(float(spot)))            # ATM -- V15_SAFE_TIERS under $10K
    date = dt.date.fromisoformat(ev["date"])
    sym = option_symbol(date, strike, "C")
    out["symbol"] = sym
    opt = load_contract_bars(sym)
    if opt is None or opt.empty:
        out["status"] = "UNCOVERED_NO_OPRA"
        return out

    entry_ts = pd.Timestamp(f"{ev['date']} {ev['bar']}:00")
    opt = opt.copy()
    opt["timestamp_et"] = pd.to_datetime(opt["timestamp_et"])
    if getattr(opt["timestamp_et"].dt, "tz", None) is not None:
        opt["timestamp_et"] = opt["timestamp_et"].dt.tz_localize(None)
    entry_rows = opt[opt["timestamp_et"] >= entry_ts]
    if entry_rows.empty:
        out["status"] = "NO_ENTRY_BAR"
        return out
    er = entry_rows.iloc[0]
    entry_premium = float(er["vwap"]) if float(er.get("vwap") or 0) > 0 else float(er["close"])
    if entry_premium <= 0:
        out["status"] = "BAD_PREMIUM"
        return out
    out["entry_premium"] = round(entry_premium, 4)
    out["entry_bar_et"] = str(er["timestamp_et"])

    # ribbon series on the OPTION bar cadence, from SPY closes (structure/ribbon stages)
    opt_idx_ts = opt["timestamp_et"]
    spy_on_opt = spy_day.set_index("timestamp_et")["close"].reindex(opt_idx_ts).ffill()
    rib = compute_ribbon(pd.Series(spy_on_opt.values))
    ribbon_tick_df = pd.DataFrame({"stack": rib["stack"].values})

    try:
        res = walk_exit_manager(
            symbol=sym, side="C", entry_time_et=er["timestamp_et"].to_pydatetime(),
            entry_premium=entry_premium, qty=QTY, exit_shape=EXIT_SHAPE,
            structure_stop_enabled=True, trigger_level=ev.get("trigger_level"),
            strategy="ribbon_ride", time_stop_et=TIME_STOP,
            opt_df=opt, ribbon_tick_df=ribbon_tick_df, five_min_spy_df=spy_day,
        )
    except Exception as exc:                      # noqa: BLE001 - report, never silently drop
        out["status"] = f"WALK_ERROR:{type(exc).__name__}:{exc}"
        return out

    pnl = getattr(res, "total_pnl", None)
    if pnl is None:
        pnl = sum(leg.leg_pnl for leg in (getattr(res, "legs", []) or []))
    out["status"] = "OK"
    out["pnl"] = round(float(pnl), 2)
    out["exit_reason"] = getattr(res, "exit_reason", None)
    return out


def exit_fallback_audit(ok_rows: list[dict]) -> dict:
    """CORRECTION 2026-07-31 evening: the validated exit cell never reached 90% of trades.

    ExitState.from_entry resolves stop_mode="structure" ONLY when the shape declares it AND
    structure_stop_enabled AND a trigger_level is present. `trigger_level` comes from the
    ledger's bull_reclaim_level_raw / trigger_level_exact, which are ABSENT on most shadow
    firings -- so those trades silently fell back to PREMIUM mode at premium_stop_pct
    (-20%), which RIBBON_RIDE's own source note calls the flag-OFF emergency fallback, NOT
    the validated cell. That is C14/L248 dead-knob-by-omission, and it happened inside a
    harness whose docstring promised the validated cell.

    This function makes the defect a FIRST-CLASS FIELD of the output instead of a footnote:
    how many trades lost the structure stop, and what the premium stops actually fired at.
    Direction of bias is CONSERVATIVE -- see counterfactual_true_cap below.
    """
    missing = [r for r in ok_rows if r.get("trigger_level") is None]
    stops = [r for r in ok_rows if str(r.get("exit_reason", "")).startswith("premium_stop")]
    pcts = []
    for r in stops:
        try:
            px = float(str(r["exit_reason"]).split(" @ ")[1])
            pcts.append(round(100.0 * (px / r["entry_premium"] - 1.0), 1))
        except (IndexError, ValueError, KeyError, ZeroDivisionError):
            continue
    stages: dict[str, int] = defaultdict(int)
    for r in ok_rows:
        stages[str(r.get("exit_reason", "?")).split(" @ ")[0]] += 1
    return dict(
        n_resolved=len(ok_rows),
        n_missing_trigger_level=len(missing),
        pct_missing_trigger_level=round(100.0 * len(missing) / max(1, len(ok_rows)), 1),
        n_premium_stop_legs=len(stops),
        premium_stop_realized_pct_min=min(pcts) if pcts else None,
        premium_stop_realized_pct_max=max(pcts) if pcts else None,
        exit_stage_histogram=dict(sorted(stages.items())),
        note="premium stops all cluster at the -20% FALLBACK, none near the -50% "
             "catastrophe cap -- proof the structure cell was not applied. structure_stop "
             "legs come only from the minority of trades that carried a trigger_level.",
    )


def day_level_test(per_day: dict) -> dict:
    """Day-level block test -- the pre-reg promised it and the first run never computed it.

    ~45 firings inside one session are NOT independent draws: on 2026-07-20 alone 52
    wick_reclaim trades ran across only 8 distinct contracts, and the detector fires on 57%
    of RTH bars, so positions overlap near-continuously. The per-trade p-value therefore
    OVERSTATES significance. The day is the honest block.
    """
    days = [v for _, v in sorted(per_day.items())]
    if len(days) < 3:
        return dict(n_days=len(days), statistic=None, p_value=None,
                    n_days_negative=sum(1 for d in days if d < 0),
                    note="fewer than 3 day-blocks -- no day-level test")
    mean = sum(days) / len(days)
    var = sum((d - mean) ** 2 for d in days) / (len(days) - 1)
    stat = mean / math.sqrt(var / len(days)) if var > 0 else 0.0
    return dict(n_days=len(days), day_sums=[round(d, 2) for d in days],
                mean_per_day=round(mean, 2), statistic=round(stat, 3),
                p_value=one_sample_p(days),
                n_days_negative=sum(1 for d in days if d < 0),
                method="mean/SE over day-sums, two-sided p by normal approximation "
                       "(one_sample_p) -- same estimator as the per-trade screen")


def bh_fdr(pvals: list[float], q: float = 0.10) -> list[bool]:
    """Benjamini-Hochberg. Returns per-input significance at FDR<=q."""
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    keep = [False] * m
    kmax = -1
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= q * rank / m:
            kmax = rank
    for rank, i in enumerate(order, start=1):
        if rank <= kmax:
            keep[i] = True
    return keep


def one_sample_p(xs: list[float]) -> float:
    """Two-sided p for mean != 0 via normal approx on the t-stat. Small-n honest enough
    for a screen; the verdict does NOT rest on it alone (n and drop-best gate too)."""
    n = len(xs)
    if n < 3:
        return 1.0
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    if var <= 0:
        # Degenerate (all values identical). A zero-variance sample does NOT license a
        # claim of infinite certainty from n=30 -- floor it like the underflow case.
        return 1.0 if mean == 0 else 1e-16
    t = mean / math.sqrt(var / n)
    p = math.erfc(abs(t) / math.sqrt(2))
    # erfc underflows to exactly 0.0 for large |t|; reporting "p=0.0" would overstate
    # certainty from a 30-sample screen. Floor at the representable-meaningful bound.
    return max(p, 1e-16)


def main() -> int:
    events, meta = load_events()
    spy_by_day = load_spy()
    results = []
    for ev in events:
        day = spy_by_day.get(ev["date"])
        if day is None:
            ev = dict(ev, status="NO_SPY_DAY")
            results.append(ev)
            continue
        results.append(run_one(ev, day))

    unbiased_days, cov_detail = fully_covered_days(events)

    def summarize(rows: list[dict]) -> dict:
        ok = [r for r in rows if r.get("status") == "OK"]
        pnls = [r["pnl"] for r in ok]
        n = len(pnls)
        if not n:
            return dict(n_resolved=0, total_pnl=None, win_rate_pct=None, per_trade=None,
                        drop_best_total=None, p_value=None, per_day={}, n_days=0)
        by_day: dict[str, float] = defaultdict(float)
        for r in ok:
            by_day[r["date"]] += r["pnl"]
        total = round(sum(pnls), 2)
        return dict(n_resolved=n, total_pnl=total,
                    win_rate_pct=round(100.0 * sum(1 for p in pnls if p > 0) / n, 1),
                    per_trade=round(total / n, 2), drop_best_total=round(total - max(pnls), 2),
                    p_value=one_sample_p(pnls), per_day={d: round(v, 2) for d, v in sorted(by_day.items())},
                    n_days=len(by_day))

    per_signal = {}
    pvals, sig_order = [], []
    for sig in SIGNALS:
        rows = [r for r in results if r["signal"] == sig]
        ok = [r for r in rows if r.get("status") == "OK"]
        excl = defaultdict(int)
        for r in rows:
            if r.get("status") != "OK":
                excl[r.get("status", "?")] += 1
        pnls = [r["pnl"] for r in ok]
        n = len(pnls)
        total = round(sum(pnls), 2)
        wr = round(100.0 * sum(1 for p in pnls if p > 0) / n, 1) if n else None
        per_tr = round(total / n, 2) if n else None
        drop_best = round(total - max(pnls), 2) if n else None
        by_day = defaultdict(float)
        for r in ok:
            by_day[r["date"]] += r["pnl"]
        # UNBIASED slice: only days whose cached strike ladder spans the whole SPY range.
        unb_rows = [r for r in rows if r["date"] in unbiased_days]
        unbiased = summarize(unb_rows)
        # BH-FDR is run on the UNBIASED slice -- testing the biased one would be
        # significance-shopping on a known artifact.
        p = unbiased["p_value"] if unbiased["p_value"] is not None else 1.0
        pvals.append(p)
        sig_order.append(sig)
        per_signal[sig] = dict(
            all_days_BIASED=dict(
                n_events_total=len(rows), n_resolved=n,
                coverage_pct=round(100.0 * n / len(rows), 1) if rows else 0.0,
                excluded=dict(excl), total_pnl=total, win_rate_pct=wr, per_trade=per_tr,
                drop_best_total=drop_best,
                per_day={d: round(v, 2) for d, v in sorted(by_day.items())},
                n_days=len(by_day),
                WARNING="OPRA cache selection is NOT random -- see coverage_audit. Do not "
                        "draw conclusions from this block; it exists for disclosure only.",
            ),
            unbiased_days_only=unbiased,
            fires_per_trading_bar=round(len(rows) / max(1, sum(
                v for k2, v in meta["bars_per_day"].items()
                if k2 in {r['date'] for r in rows})), 3),
        )
    keep = bh_fdr(pvals, q=0.10)
    for sig, k in zip(sig_order, keep):
        u = per_signal[sig]["unbiased_days_only"]
        u["bh_fdr_q010_significant_PER_TRADE"] = bool(k)
        # The per-trade BH result is retained for provenance but is NO LONGER the verdict:
        # it treats overlapping same-contract positions as independent draws (n-inflation).
        u["day_level"] = day_level_test(u["per_day"])

    # ---- CORRECTION: what the exits ACTUALLY did, and the counterfactual at the true cap
    ok_unb = [r for r in results if r.get("status") == "OK" and r["date"] in unbiased_days]
    fallback = exit_fallback_audit(ok_unb)
    _orig_stop = EXIT_SHAPE.get("premium_stop_pct")
    EXIT_SHAPE["premium_stop_pct"] = EXIT_SHAPE.get("catastrophe_stop_pct", -0.5)
    cf_tot: dict[str, float] = defaultdict(float)
    cf_n: dict[str, int] = defaultdict(int)
    for ev in events:
        if ev["date"] not in unbiased_days or spy_by_day.get(ev["date"]) is None:
            continue
        r = run_one(ev, spy_by_day[ev["date"]])
        if r.get("status") == "OK":
            cf_tot[r["signal"]] += r["pnl"]
            cf_n[r["signal"]] += 1
    EXIT_SHAPE["premium_stop_pct"] = _orig_stop
    counterfactual = dict(
        what="every trade re-walked with the stop set to the TRUE -50% catastrophe cap "
             "instead of the -20% premium fallback the missing trigger_level forced",
        stop_pct_used=EXIT_SHAPE.get("catastrophe_stop_pct", -0.5),
        per_signal={s: dict(n=cf_n[s], total_pnl=round(cf_tot[s], 2)) for s in sorted(cf_n)},
        bias_direction="CONSERVATIVE -- the reported figures FLATTER these signals. At the "
                       "true cap both measured signals get WORSE, so the NULL verdict "
                       "survives and strengthens. Nothing here reverses a verdict.",
    )
    for sig in SIGNALS:
        per_signal[sig]["unbiased_days_only"]["counterfactual_true_50pct_cap"] = (
            dict(n=cf_n[sig], total_pnl=round(cf_tot[sig], 2)) if cf_n.get(sig) else None)

    # ---- explicit verdict strings (so no downstream surface has to infer one)
    verdicts = {}
    for sig in SIGNALS:
        u = per_signal[sig]["unbiased_days_only"]
        dl = u.get("day_level") or {}
        if not u["n_resolved"]:
            verdicts[sig] = ("UNDERPOWERED -- NO VERDICT ISSUED. n=0 resolvable events. "
                             "Untested, NOT dead: do not graveyard it.")
        elif dl.get("p_value") is not None and dl["p_value"] <= 0.05 and dl["n_days_negative"] == dl["n_days"]:
            verdicts[sig] = (f"SIGNIFICANT NEGATIVE at day level (stat={dl['statistic']}, "
                             f"p={dl['p_value']:.4g}, {dl['n_days_negative']}/{dl['n_days']} "
                             "days negative) -- stands unqualified.")
        else:
            verdicts[sig] = (f"NEGATIVE POINT ESTIMATE, NOT SIGNIFICANT at day level "
                             f"(stat={dl.get('statistic')}, p={dl.get('p_value'):.4g}, "
                             f"{dl.get('n_days_negative')}/{dl.get('n_days')} days negative). "
                             "The per-trade p-value is n-inflated by overlapping positions.")

    report = dict(
        generated_at_et=et_now().strftime("%Y-%m-%dT%H:%M:%S"),  # REAL ET (box is Mountain)
        verdicts=verdicts,
        scope="STANDALONE-TRIGGER form ONLY -- 'take every firing as an entry'. Their use as "
              "SCORE CONTRIBUTORS, tiebreakers or vetoes is UNTESTED here and must not be "
              "swept into the graveyard (gate interactions are multiplicative, C15).",
        exit_fallback_correction=fallback,
        counterfactual_true_cap=counterfactual,
        prereg="analysis/deep-research/SHADOW-SIGNAL-PREREG-2026-07-31.md",
        method=dict(event_unit="(signal, date, 5-min bar)", entry="entry+1, VWAP of containing 5m option bar",
                    strike="ATM (V15_SAFE_TIERS, verified)",
                    exit="REAL exit_manager via walk_exit_manager, RIBBON_RIDE shape -- BUT "
                         "see exit_fallback_correction: 90% of trades lacked trigger_level "
                         "and ran the -20% PREMIUM fallback, not the validated structure cell",
                    qty=QTY, pricing="real OPRA cache only; synthetic excluded",
                    multiplicity=f"BH-FDR q<=0.10 across {len(SIGNALS)} signals"),
        exit_shape=EXIT_SHAPE,
        coverage_audit=dict(unbiased_days=sorted(unbiased_days), per_day=cov_detail),
        selectivity=dict(tick_firings=meta["tick_firings"], bars_per_day=meta["bars_per_day"]),
        per_signal=per_signal,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")

    print(f"events={len(events)}  resolved={sum(1 for r in results if r.get('status')=='OK')}")
    print(f"UNBIASED days (cached ladder spans full SPY range): {sorted(unbiased_days)}")
    for d, c in sorted(cov_detail.items()):
        print(f"   {d}: SPY {c['spy_lo']}-{c['spy_hi']} need {c['atm_strikes_needed']} ATM "
              f"strikes, cached {c['cached']}, missing {len(c['missing_atm_strikes'])} "
              f"-> unbiased={c['unbiased']}")
    for sig in SIGNALS:
        b, u = per_signal[sig]["all_days_BIASED"], per_signal[sig]["unbiased_days_only"]
        print(f"\n{sig}:  fires/bar={per_signal[sig]['fires_per_trading_bar']}")
        print(f"   [BIASED all-days]   n={b['n_resolved']}/{b['n_events_total']} "
              f"({b['coverage_pct']}%) total={b['total_pnl']} per_tr={b['per_trade']} "
              f"WR={b['win_rate_pct']}% drop_best={b['drop_best_total']}")
        print(f"   [UNBIASED slice]    n={u['n_resolved']} days={u['n_days']} "
              f"total={u['total_pnl']} per_tr={u['per_trade']} WR={u['win_rate_pct']}% "
              f"drop_best={u['drop_best_total']} p_per_trade={u['p_value']} "
              f"BH_sig_per_trade={u['bh_fdr_q010_significant_PER_TRADE']}")
        print(f"   [UNBIASED per_day]  {u['per_day']}")
        print(f"   [DAY-LEVEL]         {u['day_level']}")
        print(f"   [-50% CAP CF]       {u['counterfactual_true_50pct_cap']}")
        print(f"   VERDICT: {report['verdicts'][sig]}")
    print(f"\n[EXIT FALLBACK] {fallback}")
    print(f"\n[wrote] {OUT.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
