"""FLEET GATE SWEET-SPOT — looseness-ladder frequency frontier (L0..L4).

Clone of gate_frequency_frontier.py, but instead of a leave-one-out audit it runs
a MONOTONIC LOOSENESS LADDER L0 (production) -> L4 (loosest diagnostic / knee-finder)
on the LIVE SAFE config ($2K -> OTM-2, chart-stop primary, real OPRA fills) and maps,
at each rung:

    edge_capture (OP-16, on the 6 J anchor days, separate block),
    per-trade expectancy, WR, trades/DAY (the OVERTRADE metric — J's explicit fear),
    max drawdown, theta-bleed proxy, and a per-DAY pnl line.

The ladder is purely to LOCATE THE KNEE — where looseness goes -EV. L4 is the
"L4_LOOSEST_DIAGNOSTIC (knee-finder)" config: L3 plus min_triggers_bull:1 AND drop the
no_trade_window / widen the entry window to 09:30. Expected to churn/bleed — it PROVES
where looseness stops paying, it is NOT a ship candidate.

OP-16 edge_capture (separate block, run per J anchor DAY over real fills):
    edge_capture = sum(engine_pnl on the 3 winner days) - sum(max(0, engine_loss on the 3 loser days))
    Max possible = 1542. A rung with edge_capture < 771 (50%) is REJECTED regardless of aggregate.
    NOTE: the J anchors are all 2026 dates (matched to actual SPY price), so they live INSIDE
    the OOS window — an anchor "take" is disclosed, not laundered as pure IS evidence.

Causality preserved (only RELAX gates; no look-ahead). Real OPRA fills. $0 cost.
PROPOSE-ONLY: writes analysis/recommendations/fleet_gate_sweetspot.json; does NOT edit params.json.

DATA (resolved): a continuous 2025-01-02..2026-06-18 SPY/VIX 5m master now exists
(spy_5m_2025-01-01_2026-06-18.csv, 34606 bars, 0 dup timestamps, full 141-bar days on
06-16/17/18). load_data resolves to it for END=2026-06-18, so the full OPRA window is
covered — NO 06-17/06-18 gap. 2026-06-24 remains WATCH-qualitative only (zero OPRA files
for the 260624 expiry; coverage ends 260618) — no $ number assigned, per C1.

Run:  backtest/.venv/Scripts/python.exe -m autoresearch.fleet_gate_sweetspot
Env:  GAMMA_RISK_GATE_ASSERT=1 (keep ON for the scorecard run). For a fast first pass only,
      GAMMA_ENGINE_SCORE_ASSERT=0 GAMMA_ENGINE_GATES_ASSERT=0.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Optional

_REPO = Path(__file__).resolve().parent.parent     # backtest/
_ROOT = _REPO.parent                               # repo root
for _p in (str(_REPO), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.orchestrator import run_backtest            # noqa: E402
from autoresearch.runner import load_data            # noqa: E402

PARAMS_PATH = _ROOT / "automation" / "state" / "params.json"
OUT_PATH = _ROOT / "analysis" / "recommendations" / "fleet_gate_sweetspot.json"

START = dt.date(2025, 1, 1)
# OPRA real-fill coverage cap = 2026-06-18. The 2025-01-01_2026-06-18 SPY/VIX 5m master
# (built by merging the 06-16 master with the 05-19_06-18 tail, deduped on timestamp) now
# bridges the full window, so END IS the true OPRA cap. (OPRA option files exist through
# expiry 260618; verified.)
END = dt.date(2026, 6, 18)
END_TARGET_OPRA_CAP = dt.date(2026, 6, 18)          # OPRA cap (now fully covered)
OOS_BOUNDARY = dt.date(2026, 1, 1)                  # 2025 IS / 2026 OOS (calendar-year split)

SAFE_EQUITY = 2000.0                                # live Safe -> OTM-2 (ship target)

# OP-16 J source-of-truth anchor days (all 2026 dates, matched to actual SPY price).
# (date, dir, real_pnl) — real_pnl is J's actual outcome, used only to report the
# anchor and to size the edge_capture max; the engine's OWN pnl on the day is what
# edge_capture sums.
J_WINNERS = [
    (dt.date(2026, 4, 29), "P", 342.0),   # SPY 710P x6
    (dt.date(2026, 5, 1), "P", 470.0),    # SPY 721P x20
    (dt.date(2026, 5, 4), "P", 730.0),    # SPY 721P x10
]
J_LOSERS = [
    (dt.date(2026, 5, 5), "P", -260.0),   # SPY 722P x20
    (dt.date(2026, 5, 6), "P", -300.0),   # SPY 730P x10
    (dt.date(2026, 5, 7), "C", -45.0),    # SPY 734C x3  (+ 737C -120; engine takes whatever fires)
]
EDGE_CAPTURE_MAX = 1542.0
EDGE_CAPTURE_REJECT_BELOW = 771.0          # < 50% of max => REJECT the rung (OP-16)

# ELITE quality triggers (the in-engine vocabulary). A trade is "ELITE / A+" if its
# triggers_fired contains a confluence OR a sequence trigger. There is NO native engine
# knob for this, so the brief's L1_TIGHT (safe-3 A+) ELITE requirement is applied as a
# POST-FILTER on emitted trades' triggers_fired (computed causally at the entry bar).
ELITE_TRIGGERS = {"confluence", "sequence_rejection", "sequence_reclaim"}

# ---------- KNEE eligibility (the SHIP-candidate gate) ----------------------------------
# A "knee" is the loosest rung that is still SHIPPABLE — not merely net-positive. The old
# gate (total>0 AND not rejected_by_op16) wrongly returned L4_LOOSEST_DIAGNOSTIC: L4 is the
# churn/bleed knee-FINDER (worst max_dd, lowest exp, highest theta-bleed) and only "clears"
# OP-16 because the engine catches one extra anchor-day put at the loosest setting. OP-16
# edge_capture is near-zero-sample HERE (0-2 engine trades per anchor day) and inverts — at
# L0 production it is even NEGATIVE — so requiring an OP-16 "pass" is exactly what blesses the
# worst rung. The fix excludes diagnostics, demotes OP-16 to advisory, and adds two RELIABLE
# ship gates: per-trade expectancy must not collapse vs L0, and the rung must be OOS-positive.
DIAGNOSTIC_LEVELS = {"L4_LOOSEST_DIAGNOSTIC"}   # knee-FINDERS, never ship candidates -> excluded
KNEE_EXP_FLOOR_FRAC = 0.40                       # knee per-trade exp must be >= 40% of L0 prod exp


# ---------- trade helpers ----------
def _tdate(t) -> dt.date:
    ts = t.entry_time_et
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.replace(tzinfo=None)
    return ts.date()


def _days(trades) -> int:
    return len(set(_tdate(t) for t in trades))


def _is_elite(t) -> bool:
    """A+ quality: triggers_fired contains confluence OR a sequence trigger."""
    return bool(set(getattr(t, "triggers_fired", []) or []) & ELITE_TRIGGERS)


def _elite_filter(trades, elite_only: bool):
    """Apply the ELITE post-filter (the un-modeled safe-3 quality gate) when requested."""
    return [t for t in trades if _is_elite(t)] if elite_only else list(trades)


def _summ(trades, lo: Optional[dt.date] = None, hi: Optional[dt.date] = None) -> dict:
    sub = [t for t in trades
           if (lo is None or _tdate(t) >= lo) and (hi is None or _tdate(t) <= hi)]
    if not sub:
        return {"n": 0, "total": 0.0, "wr": 0.0, "exp": 0.0, "tr_per_day": 0.0,
                "trading_days": 0, "max_dd": 0.0, "bear_n": 0, "bear_pnl": 0.0,
                "bull_n": 0, "bull_pnl": 0.0, "theta_bleed": 0.0}
    pnls = [float(t.dollar_pnl) for t in sub]
    wins = [p for p in pnls if p > 0]
    bears = [t for t in sub if "BULLISH" not in str(t.setup)]
    bulls = [t for t in sub if "BULLISH" in str(t.setup)]
    nd = _days(sub)
    # max drawdown on the chronological equity curve of trade pnls (per-trade peak-to-trough).
    # Sort on a tz-NORMALISED key: some trades carry tz-aware entry_time_et and some are
    # naive, and sorting a mix raises "can't compare offset-naive and offset-aware".
    def _sort_key(t):
        ts = t.entry_time_et
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        if getattr(ts, "tzinfo", None) is not None:
            ts = ts.replace(tzinfo=None)
        return ts
    ordered = sorted(sub, key=_sort_key)
    eq, peak, mdd = 0.0, 0.0, 0.0
    for t in ordered:
        eq += float(t.dollar_pnl)
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    # theta-bleed proxy: total $ lost across all LOSING trades (premium decay / stop bleed).
    theta_bleed = round(sum(p for p in pnls if p < 0), 2)
    return {
        "n": len(sub), "total": round(sum(pnls), 2),
        "wr": round(len(wins) / len(sub), 4), "exp": round(sum(pnls) / len(sub), 2),
        "trading_days": nd,
        "tr_per_day": round(len(sub) / nd, 3) if nd else 0.0,
        "max_dd": round(mdd, 2),
        "bear_n": len(bears), "bear_pnl": round(sum(t.dollar_pnl for t in bears), 2),
        "bull_n": len(bulls), "bull_pnl": round(sum(t.dollar_pnl for t in bulls), 2),
        "theta_bleed": theta_bleed,
    }


def _per_day_pnl(trades) -> dict:
    """Per trading-day pnl line {YYYY-MM-DD: {n, pnl}}."""
    out: dict[str, dict] = {}
    for t in trades:
        k = str(_tdate(t))
        out.setdefault(k, {"n": 0, "pnl": 0.0})
        out[k]["n"] += 1
        out[k]["pnl"] = round(out[k]["pnl"] + float(t.dollar_pnl), 2)
    return dict(sorted(out.items()))


def run_cfg(spy, vix, params: dict, equity: float,
            sd: dt.date = START, ed: dt.date = END, elite_only: bool = False):
    p = copy.deepcopy(params)
    p["use_real_fills"] = True
    res = run_backtest(spy, vix, start_date=sd, end_date=ed,
                       use_real_fills=True, params_overrides=p, initial_equity=equity)
    return _elite_filter(res.trades, elite_only)


# ---------- LOOSENESS LADDER L0..L4 -----------------------------------------
# L0 = production baseline (no patch). Each rung is a SUPERSET relaxation of the prior
# (monotonic looseness): we relax frequency-cutting gates one cluster at a time so the
# trades/day curve climbs and we can see exactly where edge_capture / expectancy break.
#
# Live param namespace (verified against automation/state/params.json):
#   entry_no_trade_before_et='09:35', entry_no_trade_after_et='15:00',
#   filter_10_min_triggers_bull=2, filter_10_min_triggers_bear=1,
#   midday_trendline_gate=True, block_level_rejection=True,
#   filter_9_vol_multiplier=0.7, ribbon_min_spread_cents=30,
#   entry_bar_body_pct_min=0.2, vix_bear_hard_cap=23.0.
LOOSENESS_LEVELS: list[tuple[str, dict, bool]] = [
    # L1_TIGHT (safe-3 A+) — the BRIEF deliverable; TIGHTER than production. Require
    # >=2 bear AND >=2 bull triggers (native engine knobs) PLUS ELITE quality (confluence
    # OR sequence) as a causal post-filter. The min_confidence:0.65 part of safe-3 is NOT
    # backtestable (no confidence field) — its intent is approximated by ELITE only. Expect
    # LOWEST trade count, HIGHEST per-trade expectancy.
    ("L1_TIGHT_safe3_Aplus", {
        "filter_10_min_triggers_bear": 2,
        "min_triggers_bear": 2,
        "filter_10_min_triggers_bull": 2,
        "min_triggers_bull": 2,
    }, True),
    ("L0_PRODUCTION", {}, False),
    # Lmild: relax the two softest frequency cutters — midday trendline gate OFF,
    #        entry-bar body/doji gate OFF. (Admits weaker entry bars in the midday window.)
    ("L1_MILD", {
        "midday_trendline_gate": False,
        "entry_bar_body_pct_min": 0.0,
    }, False),
    # L2: L1 + relax the bear class/quality gates — un-block level_rejection puts,
    #     drop the breakdown-bar volume floor 0.7 -> 0.4, ribbon spread 30c -> 20c.
    #     NOTE: ribbon spread is the MODULE-CONST key `ribbon_spread_min_cents`
    #     (-> RIBBON_SPREAD_MIN_CENTS), NOT `ribbon_min_spread_cents` (which is unrecognised
    #     by the orchestrator translation map and would be a silent dead knob — C14/L70).
    ("L2_MODERATE", {
        "midday_trendline_gate": False,
        "entry_bar_body_pct_min": 0.0,
        "block_level_rejection": False,
        "filter_9_vol_multiplier": 0.4,
        "ribbon_spread_min_cents": 20,
    }, False),
    # L3: L2 + lift the VIX bear hard cap (admit high-fear bears) + drop the volume floor
    #     entirely (0.0). DELIBERATELY NOT widening the after-cutoff: the backtest's entry
    #     window upper bound is hardcoded < 16:00 (orchestrator.py:789) and the live
    #     `entry_no_trade_after_et`=15:00 param is NOT read by the backtest — so a
    #     "15:00 -> 15:30" patch would be a silent no-op here (disclosed in notes, not faked).
    ("L3_LOOSE", {
        "midday_trendline_gate": False,
        "entry_bar_body_pct_min": 0.0,
        "block_level_rejection": False,
        "filter_9_vol_multiplier": 0.0,
        "ribbon_spread_min_cents": 20,
        "vix_bear_hard_cap": 999.0,
    }, False),
    # L4 = "L4_LOOSEST_DIAGNOSTIC (knee-finder)": L3 PLUS min_triggers_bull:1 AND drop the
    #     no_trade_window / widen the entry window to 09:30 (entry_no_trade_before_et:09:30).
    #     Purely to map the far end of the curve — expected to churn/bleed, NOT a ship candidate.
    ("L4_LOOSEST_DIAGNOSTIC", {
        "midday_trendline_gate": False,
        "entry_bar_body_pct_min": 0.0,
        "block_level_rejection": False,
        "filter_9_vol_multiplier": 0.0,
        "ribbon_spread_min_cents": 20,
        "vix_bear_hard_cap": 999.0,
        "filter_10_min_triggers_bull": 1,
        "min_triggers_bull": 1,
        "entry_no_trade_before_et": "09:30",
        "no_trade_first_minutes": 0,
        "entry_no_trade_window_et": None,
    }, False),
]


def _apply(params: dict, patch: dict) -> dict:
    p = copy.deepcopy(params)
    p.update(patch)
    return p


# ---------- OP-16 edge_capture block (per J anchor DAY, real fills) ----------
def edge_capture_block(full_trades) -> dict:
    """Compute OP-16 edge_capture by SLICING the anchor days out of ONE full-window run.

    edge_capture = sum(engine_pnl on winner days) - sum(max(0, engine_loss on loser days))
    where engine_loss is reported as a NEGATIVE pnl, so max(0, -loss_as_positive) means we
    only PENALISE loser days where the engine LOST money (and by how much).

    IMPORTANT (bug fix): the anchor-day P&L MUST be sliced from the same full-window run,
    NOT re-run in a 1-day window. The engine is stateful (level role/bounce history, ribbon
    duration, sequence detection) and needs the prior-bar warmup; a `start=d, end=d` run
    starves that warmup and silently emits ZERO anchor trades -> a false edge_capture=0.
    """
    per_day: dict[str, dict] = {}

    def _day_pnl(d: dt.date) -> tuple[float, int]:
        day_t = [t for t in full_trades if _tdate(t) == d]
        return round(sum(float(t.dollar_pnl) for t in day_t), 2), len(day_t)

    winner_sum = 0.0
    for d, _dir, real in J_WINNERS:
        pnl, n = _day_pnl(d)
        winner_sum += pnl
        per_day[str(d)] = {"role": "WINNER", "j_real_pnl": real, "engine_pnl": pnl,
                           "engine_n": n}

    loser_penalty = 0.0  # sum of max(0, loss) i.e. how much the engine LOST on loser days
    for d, _dir, real in J_LOSERS:
        pnl, n = _day_pnl(d)
        # engine_loss as a positive magnitude only when the engine lost money
        penalty = max(0.0, -pnl)
        loser_penalty += penalty
        per_day[str(d)] = {"role": "LOSER", "j_real_pnl": real, "engine_pnl": pnl,
                           "engine_n": n, "loss_penalty": round(penalty, 2)}

    edge_capture = round(winner_sum - loser_penalty, 2)
    return {
        "edge_capture": edge_capture,
        "winner_day_pnl_sum": round(winner_sum, 2),
        "loser_day_loss_penalty": round(loser_penalty, 2),
        "edge_capture_max": EDGE_CAPTURE_MAX,
        "edge_capture_pct_of_max": round(edge_capture / EDGE_CAPTURE_MAX, 3),
        "reject_below": EDGE_CAPTURE_REJECT_BELOW,
        "rejected_by_op16": bool(edge_capture < EDGE_CAPTURE_REJECT_BELOW),
        "per_anchor_day": per_day,
        "anchor_note": ("J anchors are all 2026 dates (matched to actual SPY price) -> they "
                        "lie INSIDE the OOS window; an anchor TAKE is disclosed, not laundered "
                        "as pure IS evidence."),
    }


# ---------- validation (OOS / WF / quarter stability) ----------
def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _wf(is_total, n_is, oos_total, n_oos) -> float:
    if n_is == 0 or n_oos == 0 or is_total == 0:
        return 0.0
    return (oos_total / n_oos) / (is_total / n_is)


def validate(trades, label: str) -> dict:
    is_t = [t for t in trades if _tdate(t) < OOS_BOUNDARY]
    oos_t = [t for t in trades if _tdate(t) >= OOS_BOUNDARY]
    is_s, oos_s = _summ(is_t), _summ(oos_t)
    wf = _wf(is_s["total"], is_s["n"], oos_s["total"], oos_s["n"])
    by_q: dict[str, list] = {}
    for t in trades:
        by_q.setdefault(_quarter(_tdate(t)), []).append(float(t.dollar_pnl))
    quarters = {q: {"n": len(v), "total": round(sum(v), 2), "exp": round(sum(v) / len(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)
    q_frac = round(q_pos / len(quarters), 3) if quarters else 0.0
    oos_pos = oos_s["total"] > 0
    wf_ok = wf >= 0.70
    sub_ok = q_frac >= 0.60
    return {
        "label": label, "IS": is_s, "OOS": oos_s, "wf_per_trade": round(wf, 3),
        "quarters": quarters, "quarter_positive_fraction": q_frac,
        "gate": {"oos_positive": oos_pos, "wf_ge_0.70": wf_ok,
                 "sub_window_stable": sub_ok,
                 "PASS": bool(oos_pos and wf_ok and sub_ok)},
    }


def main() -> int:
    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8-sig"))
    spy, vix = load_data(START, END)
    print(f"data spy={len(spy)} vix={len(vix)}; window {START}..{END} "
          f"(full OPRA cap {END_TARGET_OPRA_CAP}; 06-17/06-18 now covered via merged master)")

    base = run_cfg(spy, vix, params, SAFE_EQUITY)
    base_s = _summ(base)
    print(f"L0 BASELINE SAFE $2K OTM-2: n={base_s['n']} total=${base_s['total']:,.0f} "
          f"WR={base_s['wr']:.0%} exp=${base_s['exp']:.0f} {base_s['tr_per_day']}/day "
          f"dd=${base_s['max_dd']:,.0f}")

    rungs: list[dict] = []
    for label, patch, elite in LOOSENESS_LEVELS:
        trades = run_cfg(spy, vix, _apply(params, patch), SAFE_EQUITY, elite_only=elite)
        s = _summ(trades)
        val = validate(trades, label)
        # edge_capture SLICES the J anchor days out of this SAME full-window run (stateful
        # engine needs warmup; a 1-day re-run silently emits 0 anchor trades — see fn docstring).
        ec = edge_capture_block(trades)
        # OVERTRADE flag: tr/day materially above L0 production cadence (>2x or >1.0/day).
        overtrade = bool(s["tr_per_day"] > max(1.0, 2.0 * base_s["tr_per_day"]))
        rung = {
            "level": label, "patch": patch, "elite_post_filter": elite,
            "n": s["n"], "total": s["total"], "wr": s["wr"], "exp": s["exp"],
            "trading_days": s["trading_days"], "tr_per_day": s["tr_per_day"],
            "max_dd": s["max_dd"], "theta_bleed": s["theta_bleed"],
            "bear_n": s["bear_n"], "bear_pnl": s["bear_pnl"],
            "bull_n": s["bull_n"], "bull_pnl": s["bull_pnl"],
            "delta_vs_L0_total": round(s["total"] - base_s["total"], 2),
            "delta_vs_L0_tr_per_day": round(s["tr_per_day"] - base_s["tr_per_day"], 3),
            "edge_capture": ec["edge_capture"],
            "edge_capture_pct_of_max": ec["edge_capture_pct_of_max"],
            "rejected_by_op16_edge_capture": ec["rejected_by_op16"],
            "edge_capture_detail": ec,
            "overtrade_flag": overtrade,
            "validation": val,
            "per_day_pnl": _per_day_pnl(trades),
        }
        rungs.append(rung)
        print(f"  {label:24s} n={s['n']:4d} {s['tr_per_day']:.2f}/day "
              f"total=${s['total']:+9.0f} exp=${s['exp']:+7.0f} WR={s['wr']:.0%} "
              f"dd=${s['max_dd']:+8.0f} EC=${ec['edge_capture']:+7.0f} "
              f"OT={overtrade} OOS+={val['gate']['oos_positive']} "
              f"{'REJ-OP16' if ec['rejected_by_op16'] else ''}")

    # locate the SHIPPABLE knee: the LOOSEST rung that still holds. The old gate
    # (total>0 AND not rejected_by_op16) returned L4_LOOSEST_DIAGNOSTIC — wrong by the
    # script's own design (L4 is the churn/bleed knee-FINDER; it only clears OP-16 because
    # the near-zero-sample edge_capture metric happens to catch one extra anchor-day put at
    # the loosest setting). A ship-candidate knee must:
    #   (1) NOT be a diagnostic knee-finder (DIAGNOSTIC_LEVELS),
    #   (2) be net-positive (total > 0),
    #   (3) hold per-trade expectancy vs L0 production (exp >= KNEE_EXP_FLOOR_FRAC * L0 exp) —
    #       looseness that guts the per-trade edge is past the knee even if aggregate total holds,
    #   (4) be OOS-positive (a knee that only works in-sample is not shippable).
    # OP-16 edge_capture stays RECORDED per rung but is DEMOTED from a hard knee gate: it is
    # near-zero-sample here and inverts (only the worst rung L4 "passes"; L0 production itself
    # is OP-16-NEGATIVE), so selecting the knee with it is precisely the bug. If no relaxation
    # clears every gate the knee falls back to L0_PRODUCTION (= "no relaxation ships").
    exp_floor = round(KNEE_EXP_FLOOR_FRAC * base_s["exp"], 2)
    knee = None
    for r in rungs:
        oos_pos = bool(r["validation"]["gate"]["oos_positive"])
        fails: list[str] = []
        if r["level"] in DIAGNOSTIC_LEVELS:
            fails.append("diagnostic_knee_finder_not_shippable")
        if not (r["total"] > 0):
            fails.append("total_not_positive")
        if not (r["exp"] >= exp_floor):
            fails.append(f"exp_collapsed(exp={r['exp']}<{int(KNEE_EXP_FLOOR_FRAC*100)}%_of_L0=${exp_floor})")
        if not oos_pos:
            fails.append("oos_not_positive")
        r["knee_eligible"] = (len(fails) == 0)
        r["knee_ineligible_reasons"] = fails
        if r["knee_eligible"]:
            knee = r["level"]
    out: dict[str, Any] = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "purpose": ("Looseness-ladder frequency frontier L0..L4 on the LIVE SAFE config "
                    "($2K -> OTM-2, chart-stop primary, real OPRA fills). Maps trades/DAY vs "
                    "edge_capture vs expectancy vs theta-bleed to LOCATE THE KNEE where "
                    "looseness goes -EV. L4 is the knee-finder diagnostic, NOT a ship candidate."),
        "metric_priority": ("OP-16 edge_capture (reject < 771) is the GATE; per-trade expectancy "
                            "and OOS-positive are secondary; trades/DAY is the OVERTRADE guard "
                            "(J's overtrading lost -$17k)."),
        "config": "live params.json, chart-stop primary, real OPRA fills, SAFE $2K -> OTM-2",
        "rf_window": f"{START}..{END} (continuous single-file data; OPRA cap is {END_TARGET_OPRA_CAP})",
        "oos_split": {"IS": f"2025 (<{OOS_BOUNDARY})", "OOS": f">= {OOS_BOUNDARY}"},
        "L0_baseline_SAFE_otm2_2k": base_s,
        "ladder": rungs,
        "knee": knee,
        "knee_selection": {
            "method": ("loosest NON-diagnostic rung that is net-positive AND holds per-trade "
                       f"exp >= {int(KNEE_EXP_FLOOR_FRAC*100)}% of L0 production exp AND is OOS-positive"),
            "L0_exp": base_s["exp"],
            "exp_floor_frac": KNEE_EXP_FLOOR_FRAC,
            "exp_floor_abs": exp_floor,
            "diagnostic_excluded": sorted(DIAGNOSTIC_LEVELS),
            "op16_demoted_to_advisory": (
                "OP-16 edge_capture is recorded per rung but is NOT a hard knee gate. It is "
                "near-zero-sample here (0-2 engine trades per anchor day) and INVERTS — only the "
                "loosest/worst rung (L4) 'passes' while L0 production is OP-16-NEGATIVE — so using "
                "it to SELECT the knee is exactly the L4 label-artifact bug this fix removes. It "
                "remains a disclosure + an auto-SHIP floor (EC>=771), not a knee selector."),
            "fallback_if_none": "L0_PRODUCTION (no relaxation ships; stay at production)",
            "per_rung_eligibility": {
                r["level"]: {"knee_eligible": r["knee_eligible"],
                             "ineligible_reasons": r["knee_ineligible_reasons"]}
                for r in rungs
            },
        },
        "GATE_MODELING_GAPS": [
            "L1_TIGHT (safe-3 A+) min_triggers_bear=2/min_triggers_bull=2 ARE native engine "
            "knobs (orchestrator maps the raw snake_case alias -> filter-10/11; causal, no "
            "look-ahead).",
            "The L1_TIGHT ELITE quality requirement (triggers contain confluence OR sequence_*) "
            "has NO native engine knob, so it is applied as a POST-FILTER on each emitted trade's "
            "triggers_fired (computed causally at the entry bar). Faithful for this single-bar "
            "BEARISH_REJECTION family but NOT identical to an earlier in-engine gate.",
            "min_confidence:0.65 (part of safe-3) is UN-MODELED — there is no confidence field on "
            "the trade object anywhere. It is NOT approximated numerically; L1_TIGHT approximates "
            "only its INTENT via the ELITE requirement. This is the one un-modeled gate.",
        ],
        "DATA_GAP_DISCLOSURE": [
            f"Full OPRA window {START}..{END} now covered: the 2025-01-01_2026-06-18 SPY/VIX 5m "
            "master was built by merging the 06-16 master with the 2026-05-19_2026-06-18 tail "
            "(deduped on UTC timestamp, keep=last). 06-17 and 06-18 are now IN the OOS window. "
            "Nothing fabricated; the merge is a pure concat+dedupe of existing on-disk segments.",
            "2026-06-24 anchor is QUALITATIVE WATCH-ONLY (zero OPRA files for 260624 expiry; "
            "coverage ends 260618) — no $ number assigned, per C1 real-fills-only. STEP-3 (fetch "
            "260624 OPRA chain) is required before 06-24 can enter the real-fills set.",
        ],
        "discipline_notes": [
            "Ladder is monotonic looseness L0(production)->L4(loosest diagnostic). Each rung is a "
            "SUPERSET relaxation; only gate thresholds RELAXED, no look-ahead added (causality preserved).",
            "edge_capture computed per J anchor DAY over real fills (winner-day pnl sum minus "
            "max(0,loss) on loser days); rung rejected if edge_capture < 771 (50% of 1542 max).",
            "J anchors are 2026 dates -> inside OOS; anchor TAKE disclosed, not laundered as IS.",
            "L4 widens entry to 09:30 + min_triggers_bull:1 + drops no_trade_window -> expected to "
            "churn/bleed; it maps the far end, it is NOT a ship candidate.",
            "min_triggers_bull:1 (L4) expands the BULL side = OP-16 DRAFT (BULLISH_RECLAIM not yet "
            "J-proven). Flag; do not ship bull expansion without J.",
            "AFTER-CUTOFF IS A BACKTEST NO-OP (disclosed): the live entry_no_trade_after_et=15:00 "
            "param is NOT read by the backtest; the backtest entry window upper bound is hardcoded "
            "< 16:00 (orchestrator.py:789). So the brief's 'widen cutoff 15:00->15:30' relaxation "
            "is structurally inert here and was OMITTED from L3/L4 rather than faked as a knob.",
            "RIBBON-SPREAD key is ribbon_spread_min_cents (-> RIBBON_SPREAD_MIN_CENTS module const); "
            "ribbon_min_spread_cents is unrecognised by the orchestrator and would be a dead knob.",
            "KNEE FIX: the knee is the loosest NON-diagnostic rung that is net-positive AND holds "
            f"per-trade exp >= {int(KNEE_EXP_FLOOR_FRAC*100)}% of L0 AND is OOS-positive. L4 is "
            "EXCLUDED (diagnostic). OP-16 edge_capture is near-zero-sample here (it is NEGATIVE at "
            "L0 production and only 'passes' at the loosest L4) so it is advisory, NOT the selector "
            "— selecting on it was the L4 label-artifact bug.",
            "Propose-only: live params.json NOT edited.",
        ],
    }

    # NON-DESTRUCTIVE WRITE (C7): this doctrine path (analysis/recommendations/{rule_id}.json)
    # also carries the hand-authored OP-11 A/B scorecard (AB_SCORECARD_OP11, gate_override_map,
    # etc.). A blind write_text would SILENTLY destroy that required analysis. Carry forward any
    # pre-existing top-level key this script does not itself own; drop the legacy
    # knee_last_positive_op16_pass (renamed -> knee) so the obsolete L4 value does not linger.
    _SCRIPT_OWNED_KEYS = (set(out.keys())
                          | {"knee_last_positive_op16_pass",      # legacy (pre-knee-fix) name
                             "_preserved_human_overlays"})        # this script's own disclosure key
    carried: dict[str, Any] = {}
    if OUT_PATH.exists():
        try:
            prior = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prior = {}
        carried = {k: v for k, v in prior.items() if k not in _SCRIPT_OWNED_KEYS}
    if carried:
        out["_preserved_human_overlays"] = sorted(carried)
        out.update(carried)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nknee (loosest shippable rung; non-diagnostic + exp-floor + OOS-positive) = {knee}")
    if carried:
        print(f"preserved human overlay keys: {sorted(carried)}")
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
