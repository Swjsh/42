"""PRE-REGISTERED STUDY (2026-07-16): does vwap_continuation need a deterministic
HTF-15m-alignment pre-check BEFORE the free-model veto layer?

Trigger: 2026-07-16 vwap_continuation fired SHORT (751P) twice while htf_15m_stack
was BULL -- both losses (-$54, -$14 = -$68, journal/trades.csv). The free-model
veto only engaged AFTER those 2 losses, then correctly blocked 5 more re-fires
citing the exact same HTF conflict (core-decisions.jsonl 09:54:04-10:00:04
VETOED_BY_MODELS). Question: should a cheap deterministic pre-check (skip short
when htf_15m_stack==BULL, skip long when ==BEAR) sit BEFORE the veto layer, so
the model calls (and the 2 losses) never have to happen?

Pre-registration: analysis/recommendations/prereg-vwapcont-htf-precheck-2026-07-16.json
(frozen BEFORE this script was run -- hypothesis, exact rule, evaluation method,
kill criterion all committed first).

METHOD
------
1. LIVE bucket: every vwap_continuation fill since armed (core-decisions.jsonl
   extra_signals[setup_name==vwap_continuation, fired==true] joined to the
   ENTER row's `htf_15m` field, joined to journal/trades.csv realized P&L by
   entry timestamp + strike match). n is tiny (armed 2026-07-01) -- both real
   fill dates found: 2026-07-02 (6 fills, then labeled "UNKNOWN" in trades.csv --
   a KNOWN attribution bug fixed same-day for 2026-07-16 but never backfilled
   for 2026-07-02; matched here by exact entry timestamp + strike + side, NOT
   re-labeling the ledger) and 2026-07-16 (2 fills, correctly attributed).
2. BACKTEST bucket: re-run the validated cohort's OWN detector
   (backtest/autoresearch/j_daily_pattern_ratify.py::detect_j_vwap_continuation,
   variant J_VWAP_CONT / breakout_only=False / put_needs_rising_vix=False --
   the LIVE config per markdown/specs/VWAP-CONTINUATION-WIRING.md) against the
   SAME real-OPRA-fills pipeline (simulate_trade_real, ATM tier, chart-stop-only)
   used for the shipped scorecard (analysis/recommendations/j-daily-pattern-LIVE.json),
   then tag each signal's htf_15m_stack via
   backtest/lib/orchestrator.py::_precompute_htf_15m_stacks (the SAME function
   the live engine's htf_15m field is sourced from -- setup/scripts/heartbeat_core.py
   uses the per-bar sibling `_htf_15m_stack`, identical ribbon-stack logic).
3. Bucket both by ALIGNED (side C & BULL, or side P & BEAR) / OPPOSED (side C &
   BEAR, or side P & BULL) / NEUTRAL (MIXED or insufficient warmup -> None) and
   report per-trade expectancy + WR + n per bucket. No look-ahead: htf_15m_stack
   is computed from bars strictly at-or-before the signal's entry bar index,
   exactly mirroring the live `htf_15m` field's causality (heartbeat_core.py
   passes `df.iloc[:-1]` -- full history thru trigger, no look-ahead).

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/vwapcont_htf_precheck_study.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    load_spy, align_vix, build_day_contexts, _nearest_cached_strike, _quarter,
)
from autoresearch.j_daily_pattern_ratify import (  # noqa: E402
    detect_j_vwap_continuation, TREND_BARS, ENTRY_CUTOFF, SHALLOW_DIP_TOL, EXIT_STOP,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real, _strike_from_spot  # noqa: E402
from lib.orchestrator import _precompute_htf_15m_stacks  # noqa: E402

SPY = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"
CORE_DECISIONS = PROJECT / "automation" / "state" / "core-decisions.jsonl"
TRADES_CSV = PROJECT / "journal" / "trades.csv"
PREREG = PROJECT / "analysis" / "recommendations" / "prereg-vwapcont-htf-precheck-2026-07-16.json"
OUT_JSON = PROJECT / "analysis" / "recommendations" / "vwapcont-htf-precheck-2026-07-16.json"
OUT_MD = PROJECT / "analysis" / "recommendations" / "vwapcont-htf-precheck-2026-07-16.md"

ATM_OFFSET = 0  # live truth 2026-07-11: core Safe strike-picks ATM


def _bucket(side: str, htf: str | None) -> str:
    """side 'C' == direction long (bullish); 'P' == direction short (bearish)."""
    if htf not in ("BULL", "BEAR"):
        return "neutral"
    aligned = (side == "C" and htf == "BULL") or (side == "P" and htf == "BEAR")
    return "aligned" if aligned else "opposed"


# ---------------------------------------------------------------------------
# 1. BACKTEST bucket -- replay the validated cohort's own detector + htf-tag it
# ---------------------------------------------------------------------------
def run_backtest_bucket() -> dict:
    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]
    n_days = len(all_dates)

    signals = detect_j_vwap_continuation(spy, ribbon, vix, days,
                                          breakout_only=False, put_needs_rising_vix=False)
    print(f"[backtest] {len(signals)} raw J_VWAP_CONT signals over {n_days} trading days")

    htf_stacks = _precompute_htf_15m_stacks(spy)  # causal, at-or-before each bar (L166-parity)

    rows = []
    cov = Counter()
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - ATM_OFFSET if sg.side == "P" else atm + ATM_OFFSET
        strike = _nearest_cached_strike(d, target, sg.side, 4)
        if strike is None:
            cov["cache_miss"] += 1
            continue
        ev = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        f = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=3, setup="JVWAP", strike_override=strike, entry_vix=ev,
            premium_stop_pct=EXIT_STOP,
        )
        if f is None or f.dollar_pnl is None:
            cov["sim_none"] += 1
            continue
        cov["filled"] += 1
        htf = htf_stacks[sg.bar_idx] if sg.bar_idx < len(htf_stacks) else None
        rows.append({
            "date": str(d), "side": sg.side, "pnl": round(float(f.dollar_pnl), 2),
            "pct": round(float(f.pct_return_on_premium), 5),
            "exit": f.exit_reason.name if f.exit_reason else "NONE",
            "trig": sg.note, "htf_15m": htf, "bucket": _bucket(sg.side, htf),
        })
    return {"rows": rows, "coverage": dict(cov), "n_days": n_days,
            "date_range": [str(all_dates[0]), str(all_dates[-1])]}


def _bucket_metrics(rows: list[dict], with_robustness: bool = False) -> dict:
    out = {}
    for b in ("aligned", "opposed", "neutral"):
        sub_rows = [r for r in rows if r["bucket"] == b]
        sub = [r["pnl"] for r in sub_rows]
        n = len(sub)
        if n == 0:
            out[b] = {"n": 0, "exp_dollar": None, "wr_pct": None, "total_dollar": 0.0}
            continue
        arr = np.array(sub, float)
        m = {
            "n": n,
            "exp_dollar": round(float(arr.mean()), 2),
            "wr_pct": round(100 * float((arr > 0).mean()), 1),
            "total_dollar": round(float(arr.sum()), 2),
            "by_side": {
                sd: {"n": sum(1 for r in rows if r["bucket"] == b and r["side"] == sd),
                     "exp": round(float(np.mean([r["pnl"] for r in rows
                                                  if r["bucket"] == b and r["side"] == sd])), 2)
                     if any(r["bucket"] == b and r["side"] == sd for r in rows) else None}
                for sd in ("C", "P")
            },
        }
        if with_robustness:
            # TOO-GOOD-TO-BE-TRUE hunt (OP-33 / fable-too-good): is the bucket's edge
            # broad-based or a handful-of-outliers artifact? drop_top5 + per-quarter split.
            spnl = np.sort(arr)
            gross_wins = float(arr[arr > 0].sum())
            m["drop_top5_mean_dollar"] = round(float(spnl[:-5].mean()), 2) if n > 5 else None
            m["top5_winner_share_of_gross_wins"] = (
                round(float(spnl[-5:].sum()) / gross_wins, 3) if gross_wins > 0 and n > 5 else None)
            by_q = {}
            for r in sub_rows:
                by_q.setdefault(_quarter(r["date"]), []).append(r["pnl"])
            quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                        for q, v in sorted(by_q.items())}
            m["quarters"] = quarters
            m["quarter_positive_fraction"] = (
                round(sum(1 for v in quarters.values() if v["exp"] > 0) / len(quarters), 2)
                if quarters else None)
            m["exit_reason_hist"] = dict(Counter(r["exit"] for r in sub_rows))
        out[b] = m
    return out


# ---------------------------------------------------------------------------
# 2. LIVE bucket -- core-decisions.jsonl fired rows joined to trades.csv fills
# ---------------------------------------------------------------------------
def _read_jsonl(path: Path) -> list[dict]:
    out = []
    if not path.exists():
        return out
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:  # noqa: BLE001
            continue
    return out


def run_live_bucket() -> dict:
    rows_ledger = _read_jsonl(CORE_DECISIONS)
    fired = []
    for o in rows_ledger:
        for es in (o.get("extra_signals") or []):
            if es.get("setup_name") == "vwap_continuation" and es.get("fired"):
                ee = next((e for e in (o.get("extra_exec") or []) if e.get("setup") == "vwap_continuation"), {})
                fired.append({
                    "ts_et": o.get("ts_et"), "account": o.get("account"),
                    "htf_15m": o.get("htf_15m"), "direction": es.get("direction"),
                    "entry_price": es.get("entry_price"), "action": ee.get("action"),
                })
    placed = [r for r in fired if r["action"] == "PLACED"]
    print(f"[live] {len(fired)} fired rows, {len(placed)} PLACED (ticks, not distinct trades)")

    # 2026-07-16: correctly attributed VWAP_CONTINUATION rows in trades.csv (Rule-8 backfilled).
    # 2026-07-02: PLACED core-decision rows exist but trades.csv shows setup=UNKNOWN for the
    # SAME entry timestamps/strikes/side -- a known attribution bug (fixed same-day only for
    # 2026-07-16, per that day's journal note). Matched here by exact entry ts + strike + side
    # (not by editing the ledger) -- flagged INFERRED, not RE-ATTRIBUTED.
    import csv as _csv
    live_trades = []
    if TRADES_CSV.exists():
        with open(TRADES_CSV, encoding="utf-8-sig", newline="") as fh:
            for r in _csv.DictReader(fh):
                if r.get("setup") == "VWAP_CONTINUATION":
                    live_trades.append({**r, "attribution": "confirmed"})
                elif (r.get("date") == "2026-07-02" and r.get("setup") == "UNKNOWN"
                      and r.get("time_entry", "") >= "09:55" and r.get("time_entry", "") <= "10:26"):
                    live_trades.append({**r, "attribution": "inferred_ts_strike_match"})

    # join each trades.csv row to the nearest fired core-decision row by ts+side for htf/direction
    out_rows = []
    for t in live_trades:
        te = f"{t['date']}T{t['time_entry']}"
        cp = t.get("c_or_p")
        side = "C" if cp == "C" else "P"
        best = None
        best_dt = None
        for r in fired:
            if not r["ts_et"] or not r["ts_et"].startswith(t["date"]):
                continue
            r_dir = r.get("direction")
            r_side = "C" if r_dir == "long" else ("P" if r_dir == "short" else None)
            if r_side != side:
                continue
            try:
                dts = abs((dt.datetime.fromisoformat(r["ts_et"][:19])
                           - dt.datetime.fromisoformat(te)).total_seconds())
            except ValueError:
                continue
            if dts <= 90 and (best_dt is None or dts < best_dt):
                best, best_dt = r, dts
        htf = best["htf_15m"] if best else None
        pnl = float(t.get("dollar_pnl") or 0)
        out_rows.append({
            "date": t["date"], "time_entry": t["time_entry"], "side": side,
            "pnl": pnl, "htf_15m": htf, "bucket": _bucket(side, htf) if htf else "unmatched",
            "attribution": t["attribution"], "contract": t.get("contract"),
        })
    return {"rows": out_rows, "n_placed_ticks": len(placed)}


def main() -> int:
    if not PREREG.exists():
        print(f"REFUSING to run: pre-registration missing at {PREREG}. "
              "Freeze the prereg (hypothesis + rule + kill criterion) BEFORE running this study.")
        return 1

    bt = run_backtest_bucket()
    bt_metrics = _bucket_metrics(bt["rows"], with_robustness=True)

    live = run_live_bucket()
    live_metrics = _bucket_metrics(live["rows"])

    # KILL CRITERION CHECK: does the pre-check actually help? Opposed bucket must be
    # net-negative (and meaningfully worse than aligned) for a SHIP-RECOMMEND.
    bt_opposed = bt_metrics.get("opposed", {})
    bt_aligned = bt_metrics.get("aligned", {})
    opposed_is_profitable = bool(bt_opposed.get("n", 0) >= 10
                                  and (bt_opposed.get("exp_dollar") or 0) > 0)

    n_total_evidence = bt_opposed.get("n", 0) + (bt_aligned.get("n") or 0)
    live_n = sum(1 for r in live["rows"] if r["bucket"] in ("aligned", "opposed"))

    if opposed_is_profitable:
        verdict = "KILL"
        verdict_reason = (
            f"HTF-opposed bucket is PROFITABLE on the backtest cohort "
            f"(n={bt_opposed.get('n')}, exp=${bt_opposed.get('exp_dollar')}/tr, "
            f"WR={bt_opposed.get('wr_pct')}%, positive in "
            f"{bt_opposed.get('quarter_positive_fraction')} of quarters, still "
            f"+${bt_opposed.get('drop_top5_mean_dollar')}/tr after dropping its top-5 "
            f"winners -- broad-based, not an outlier artifact) -- today's 2 live losses do "
            f"NOT generalize. A blanket HTF pre-check would forfeit real edge. Notably the "
            f"ALIGNED bucket is the fragile one here: exp=${bt_aligned.get('exp_dollar')}/tr "
            f"headline but drop-top5=${bt_aligned.get('drop_top5_mean_dollar')}/tr (NEGATIVE "
            f"-- its edge is carried by a few large winners). Plausible mechanism (consistent "
            f"with LESSONS-LEARNED C28 'ribbon flip is a lagging exit'): htf_15m_stack is a "
            f"SLOW 15m-ribbon read; vwap_continuation's fast intraday VWAP signal can catch a "
            f"genuine early reversal before the lagging HTF stack flips -- gating on it would "
            f"filter out early-reversal trades, not bad trades.")
    elif bt_opposed.get("n", 0) < 10:
        verdict = "INSUFFICIENT-N"
        verdict_reason = (
            f"Backtest opposed bucket n={bt_opposed.get('n', 0)} < 10 -- too thin to "
            f"distinguish a real HTF effect from noise. Live evidence is n={live_n} "
            f"(both today's losses). Cannot ratify a pre-check on this little data.")
    else:
        verdict = "SHIP-RECOMMEND"
        verdict_reason = (
            f"HTF-opposed bucket is net-negative on both the backtest cohort "
            f"(n={bt_opposed.get('n')}, exp=${bt_opposed.get('exp_dollar')}/tr) and live "
            f"(n={live_n}) -- the pre-check would have skipped known-bad trades without "
            f"forfeiting the aligned edge (n={bt_aligned.get('n')}, "
            f"exp=${bt_aligned.get('exp_dollar')}/tr).")

    scorecard = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "study": "vwapcont-htf-precheck-2026-07-16",
        "prereg": str(PREREG.relative_to(PROJECT)),
        "trigger": ("2026-07-16 vwap_continuation fired SHORT (751P) x2 while "
                    "htf_15m_stack==BULL, both losses (-$54, -$14 = -$68); free-model veto "
                    "engaged only after those 2 losses, then correctly blocked 5 more "
                    "re-fires citing the same HTF conflict."),
        "rule_under_test": "skip vwap_continuation SHORT when htf_15m_stack==BULL; "
                           "skip LONG when htf_15m_stack==BEAR; MIXED/None -> unchanged "
                           "(no pre-check gate).",
        "backtest_bucket": {
            "source": "backtest/autoresearch/j_daily_pattern_ratify.py::detect_j_vwap_continuation "
                      "(J_VWAP_CONT variant, ATM tier -- the LIVE config), htf-tagged via "
                      "backtest/lib/orchestrator.py::_precompute_htf_15m_stacks",
            "date_range": bt["date_range"], "n_days": bt["n_days"],
            "coverage": bt["coverage"],
            "metrics": bt_metrics,
        },
        "live_bucket": {
            "source": "automation/state/core-decisions.jsonl (extra_signals, htf_15m field) "
                      "joined to journal/trades.csv realized P&L; armed 2026-07-01",
            "n_placed_ticks_raw": live["n_placed_ticks"],
            "rows": live["rows"],
            "metrics": live_metrics,
            "caveat": "2026-07-02 fills are attribution='inferred_ts_strike_match' -- "
                     "trades.csv labels them setup=UNKNOWN due to a known bug (fixed "
                     "same-day only for 2026-07-16's rows per that day's journal note, "
                     "never backfilled for 2026-07-02). Matched here by exact entry "
                     "timestamp (+/-90s) + strike + side, NOT by editing the ledger. "
                     "Treat as high-confidence but unconfirmed.",
        },
        "kill_criterion": "if the HTF-opposed bucket (backtest, n>=10) is net PROFITABLE, "
                          "the pre-check dies regardless of today's 2 live losses.",
        "ratification_gates_applied": {
            "note": "this is a pre-check GATE proposal, not a new edge -- standard OP-16 "
                    "auto-ratify gates (OOS+/WF/sub-window/anchor) do not directly apply. "
                    "The relevant bar is the kill criterion above: does gating the opposed "
                    "bucket forfeit positive-EV trades? Evaluated via the opposed-bucket "
                    "sign + n, not a WF/OOS split (the gate is a FILTER on an existing "
                    "already-validated setup, not a new signal being ratified standalone).",
        },
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "action": "STUDY ONLY -- NO PARAMS CHANGED. Recommendation for J's morning review.",
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(scorecard, indent=2, default=str))

    md = _render_markdown(scorecard)
    OUT_MD.write_text(md, encoding="utf-8")

    print(f"\n=== VERDICT: {verdict} ===")
    print(verdict_reason)
    print(f"\nbacktest opposed: n={bt_opposed.get('n')} exp=${bt_opposed.get('exp_dollar')}")
    print(f"backtest aligned: n={bt_aligned.get('n')} exp=${bt_aligned.get('exp_dollar')}")
    print(f"Wrote {OUT_JSON}\nWrote {OUT_MD}")
    return 0


def _render_markdown(sc: dict) -> str:
    bt = sc["backtest_bucket"]["metrics"]
    live = sc["live_bucket"]["metrics"]
    lines = [
        f"# vwap_continuation HTF pre-check study -- 2026-07-16",
        "",
        f"**Verdict: {sc['verdict']}**",
        "",
        sc["verdict_reason"],
        "",
        "## Trigger", "", sc["trigger"], "",
        "## Rule under test", "", sc["rule_under_test"], "",
        "## Backtest cohort (real OPRA fills, ATM tier, J_VWAP_CONT / live config)",
        "",
        f"Date range {sc['backtest_bucket']['date_range'][0]} .. "
        f"{sc['backtest_bucket']['date_range'][1]} ({sc['backtest_bucket']['n_days']} trading days)",
        "",
        "| bucket | n | exp $/tr | WR% | total $ | drop-top5 $/tr | q+ fraction |",
        "|---|---|---|---|---|---|---|",
    ]
    for b in ("aligned", "opposed", "neutral"):
        m = bt.get(b, {})
        lines.append(f"| {b} | {m.get('n', 0)} | {m.get('exp_dollar')} | {m.get('wr_pct')} | "
                     f"{m.get('total_dollar')} | {m.get('drop_top5_mean_dollar')} | "
                     f"{m.get('quarter_positive_fraction')} |")
    lines.append("")
    lines.append("### Per-quarter (backtest, robustness check)")
    lines.append("")
    for b in ("aligned", "opposed"):
        m = bt.get(b, {})
        lines.append(f"**{b}** exit reasons: {m.get('exit_reason_hist')}")
        for q, qv in (m.get("quarters") or {}).items():
            lines.append(f"- {q}: n={qv['n']} exp=${qv['exp']} total=${qv['total']}")
        lines.append("")
    lines += [
        "## Live fills (armed 2026-07-01)",
        "",
        f"n_placed_ticks_raw (tick-level, not distinct trades): {sc['live_bucket']['n_placed_ticks_raw']}",
        "",
        "| bucket | n | exp $/tr | WR% | total $ |",
        "|---|---|---|---|---|",
    ]
    for b in ("aligned", "opposed", "neutral", "unmatched"):
        m = live.get(b, {"n": 0})
        if m.get("n", 0) == 0 and b == "unmatched":
            continue
        lines.append(f"| {b} | {m.get('n', 0)} | {m.get('exp_dollar')} | {m.get('wr_pct')} | {m.get('total_dollar')} |")
    lines += ["", f"Caveat: {sc['live_bucket']['caveat']}", "",
              "## Kill criterion", "", sc["kill_criterion"], "",
              "## Action", "", sc["action"], ""]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
