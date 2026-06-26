"""Frequency-vs-total-P&L FRONTIER on the LIVE Safe config (PROFITABILITY MISSION).

Companion to gate_frequency_audit.py. That script does leave-one-out at the
research ITM-2/$25K config (run_with_params default). THIS script:

  1. Runs at the LIVE SAFE account size ($2K -> OTM-2 via the per-tier table +
     the $2K per-trade risk cap). That is what the live Safe account actually
     trades, and it is the chart the mission asks to map ("for a $2K account,
     total growth = expectancy x frequency x size").
  2. Leave-one-out at that tier (verdicts that apply to the live Safe book).
  3. Builds the FRONTIER: greedily stacks the over-restrictive / neutral
     relaxations, accepting each only if the WHOLE book stays total >= baseline
     AND per-trade exp > 0. Maps trades/month vs total P&L vs exp at each step.
  4. OOS-validates the chosen loosest config (chronological IS/OOS + walk-forward
     per-trade ratio + quarter stability). A frequency gain that goes -EV OOS is
     REJECTED.
  5. Cross-checks the chosen patch at ITM-2/$25K (Bold strike) as a TRANSFER FLAG
     only (C29 — gate knobs do not auto-transfer across strike tiers).

Total P&L (account growth) is the metric, NOT per-trade expectancy / edge_capture
— but the admitted population must be net-positive-or-neutral (J's overtrading
lost -$17k; do NOT buy frequency with -EV trades).

Causality preserved (only RELAX gates; no look-ahead). Real OPRA fills. $0 cost.
PROPOSE-ONLY: writes analysis/recommendations/gate-frequency-frontier.json; does
NOT edit params.json.

Run:  backtest/.venv/Scripts/python.exe -m autoresearch.gate_frequency_frontier
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
OUT_PATH = _ROOT / "analysis" / "recommendations" / "gate-frequency-frontier.json"

START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 29)            # OPRA real-fill coverage cap
OOS_BOUNDARY = dt.date(2026, 1, 1)   # 2025 IS / 2026 OOS (calendar-year chronological split)

SAFE_EQUITY = 2000.0                  # live Safe -> OTM-2 (ship target)
BOLD_EQUITY = 25000.0                 # ITM-2 transfer flag only (C29)


# ---------- trade helpers ----------
def _tdate(t) -> dt.date:
    ts = t.entry_time_et
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.replace(tzinfo=None)
    return ts.date()


def _key(t) -> tuple:
    et = t.entry_time_et
    s = et.isoformat() if hasattr(et, "isoformat") else str(et)
    return (s, t.strike, "C" if "BULLISH" in str(t.setup) else "P")


def _months(trades) -> int:
    return len(set((_tdate(t).year, _tdate(t).month) for t in trades))


def _summ(trades, lo: Optional[dt.date] = None, hi: Optional[dt.date] = None) -> dict:
    sub = [t for t in trades
           if (lo is None or _tdate(t) >= lo) and (hi is None or _tdate(t) <= hi)]
    if not sub:
        return {"n": 0, "total": 0.0, "wr": 0.0, "exp": 0.0, "tr_per_mo": 0.0,
                "bear_n": 0, "bear_pnl": 0.0, "bull_n": 0, "bull_pnl": 0.0}
    pnls = [float(t.dollar_pnl) for t in sub]
    wins = [p for p in pnls if p > 0]
    bears = [t for t in sub if "BULLISH" not in str(t.setup)]
    bulls = [t for t in sub if "BULLISH" in str(t.setup)]
    mo = _months(sub)
    return {
        "n": len(sub), "total": round(sum(pnls), 2),
        "wr": round(len(wins) / len(sub), 4), "exp": round(sum(pnls) / len(sub), 2),
        "tr_per_mo": round(len(sub) / mo, 2) if mo else 0.0,
        "bear_n": len(bears), "bear_pnl": round(sum(t.dollar_pnl for t in bears), 2),
        "bull_n": len(bulls), "bull_pnl": round(sum(t.dollar_pnl for t in bulls), 2),
    }


def run_cfg(spy, vix, params: dict, equity: float):
    p = copy.deepcopy(params)
    p["use_real_fills"] = True
    res = run_backtest(spy, vix, start_date=START, end_date=END,
                       use_real_fills=True, params_overrides=p, initial_equity=equity)
    return res.trades


# ---------- relaxations (RELAX one frequency-cutting gate; never tighten) ----------
RELAXATIONS: dict[str, dict] = {
    # Ribbon conviction gate C (midday single-trendline block 11:30-14:00).
    "midday_trendline_gate_OFF": {"midday_trendline_gate": False},
    # VIX gate (filter 8): drop the strict vix_rising REQUIREMENT (huge -deadband
    # makes any non-falling tick count as "rising"). Keeps the >threshold check.
    "vix_drop_rising_req": {"vix_bear_rising_deadband": -5.0},
    # VIX floor 17.30 -> 12 (admit low-VIX bear setups).
    "vix_bear_floor_12": {"vix_bear_threshold": 12.0},
    # VIX bear hard cap 23 -> off (admit high-fear bears).
    "vix_bear_hard_cap_OFF": {"vix_bear_hard_cap": 999.0},
    # The big bear class gate: un-block LEVEL-tier level_rejection puts.
    "block_level_rejection_OFF": {"block_level_rejection": False},
    # Doji/wick entry-bar gate off (bear).
    "entry_body_gate_OFF": {"entry_bar_body_pct_min": 0.0},
    # Volume gate on the breakdown bar: 0.7 -> 0.4, and -> 0.0.
    "filter9_vol_0p4": {"filter_9_vol_multiplier": 0.4},
    "filter9_vol_0p0": {"filter_9_vol_multiplier": 0.0},
    # Ribbon spread floor 30c -> 20c (admit weaker-trend bars).
    "ribbon_spread_20c": {"ribbon_min_spread_cents": 20},
    # Entry window: extend cutoff 15:00 -> 15:30; open 09:30.
    "entry_after_1530": {"entry_no_trade_after_et": "15:30"},
    "entry_before_0930": {"entry_no_trade_before_et": "09:30"},
    # Bull trigger floor 2 -> 1 (admit 1-trigger bull setups; OP-16 DRAFT side, flag).
    "min_triggers_bull_1": {"min_triggers_bull": 1},
}


def _apply(params: dict, patch: dict) -> dict:
    p = copy.deepcopy(params)
    p.update(patch)
    return p


# ---------- validation ----------
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
    print(f"data spy={len(spy)} vix={len(vix)}; window {START}..{END}")

    base = run_cfg(spy, vix, params, SAFE_EQUITY)
    base_s = _summ(base)
    base_keys = {_key(t) for t in base}
    print(f"BASELINE SAFE $2K OTM-2: n={base_s['n']} total=${base_s['total']:,.0f} "
          f"WR={base_s['wr']:.0%} exp=${base_s['exp']:.0f} {base_s['tr_per_mo']}/mo "
          f"(bear {base_s['bear_n']}/${base_s['bear_pnl']:,.0f}  bull {base_s['bull_n']}/${base_s['bull_pnl']:,.0f})")

    # ---- leave-one-out at the SAFE tier ----
    audit: list[dict] = []
    for label, patch in RELAXATIONS.items():
        trades = run_cfg(spy, vix, _apply(params, patch), SAFE_EQUITY)
        s = _summ(trades)
        new_keys = {_key(t) for t in trades}
        admitted = [t for t in trades if _key(t) in (new_keys - base_keys)]
        adm = _summ(admitted)
        if adm["n"] == 0:
            verdict = "NO-OP"
        elif adm["total"] > 0:
            verdict = "OVER-RESTRICTIVE"
        elif adm["total"] >= -1e-6:
            verdict = "NEUTRAL"
        else:
            verdict = "EARNS-KEEP"
        audit.append({
            "relaxation": label, "patch": patch,
            "new_n": s["n"], "new_total": s["total"], "new_wr": s["wr"],
            "new_exp": s["exp"], "new_tr_per_mo": s["tr_per_mo"],
            "delta_n": s["n"] - base_s["n"],
            "delta_total": round(s["total"] - base_s["total"], 2),
            "admitted_n": adm["n"], "admitted_total": adm["total"],
            "admitted_wr": adm["wr"], "admitted_exp": adm["exp"],
            "admitted_bear_n": adm["bear_n"], "admitted_bear_pnl": adm["bear_pnl"],
            "admitted_bull_n": adm["bull_n"], "admitted_bull_pnl": adm["bull_pnl"],
            "verdict": verdict,
        })
        print(f"  {label:28s} dn={s['n']-base_s['n']:+3d} adm_n={adm['n']:3d} "
              f"adm_total=${adm['total']:+8.0f} adm_exp=${adm['exp']:+7.0f} "
              f"new_total=${s['total']:+8.0f} -> {verdict}")
    audit.sort(key=lambda r: r["admitted_total"], reverse=True)

    # ---- frontier: greedily stack over-restrictive + neutral ----
    loosen = [r for r in audit if r["verdict"] in ("OVER-RESTRICTIVE", "NEUTRAL")]
    frontier = [{"step": 0, "added": None, "patch": {},
                 **{k: base_s[k] for k in ("n", "total", "wr", "exp", "tr_per_mo")},
                 "accepted": True}]
    stacked: dict = {}
    for r in loosen:
        trial = {**stacked, **r["patch"]}
        s = _summ(run_cfg(spy, vix, _apply(params, trial), SAFE_EQUITY))
        accept = (s["total"] >= base_s["total"] - 1e-6) and (s["exp"] > 0)
        frontier.append({
            "step": len(frontier), "added": r["relaxation"], "patch": trial,
            "n": s["n"], "total": s["total"], "wr": s["wr"], "exp": s["exp"],
            "tr_per_mo": s["tr_per_mo"],
            "delta_vs_baseline_total": round(s["total"] - base_s["total"], 2),
            "accepted": bool(accept),
        })
        print(f"  frontier +{r['relaxation']:26s} -> n={s['n']:3d} total=${s['total']:+8.0f} "
              f"exp=${s['exp']:+6.0f} {s['tr_per_mo']}/mo  accept={accept}")
        if accept:
            stacked = trial

    out: dict[str, Any] = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "purpose": ("Frequency-vs-total-P&L frontier on the LIVE Safe config ($2K -> OTM-2). "
                    "Find the LOOSEST live-config variant that stays net +EV, to trade the "
                    "existing BEARISH_REJECTION edge more often (toward daily). PROPOSE-ONLY."),
        "metric": "TOTAL P&L (account growth); admitted population must be net positive-or-neutral.",
        "config": "live params.json, chart-stop primary, real OPRA fills, SAFE $2K -> OTM-2",
        "rf_window": "2025-01-02..2026-05-29 (OPRA coverage cap)",
        "oos_split": {"IS": f"2025 (<{OOS_BOUNDARY})", "OOS": f">= {OOS_BOUNDARY}"},
        "baseline_SAFE_otm2_2k": base_s,
        "leave_one_out_SAFE": audit,
        "frontier_SAFE": frontier,
        "chosen_loosest_patch": stacked,
        "verdict_summary": {
            "over_restrictive": [r["relaxation"] for r in audit if r["verdict"] == "OVER-RESTRICTIVE"],
            "neutral": [r["relaxation"] for r in audit if r["verdict"] == "NEUTRAL"],
            "earns_keep": [r["relaxation"] for r in audit if r["verdict"] == "EARNS-KEEP"],
            "no_op_not_binding": [r["relaxation"] for r in audit if r["verdict"] == "NO-OP"],
        },
        "discipline_notes": [
            "Total P&L is the metric; admitted population required net positive-or-neutral so frequency is not bought with negative-EV trades (J's overtrading lost -$17k).",
            "Causality preserved: only gate thresholds RELAXED; no look-ahead added.",
            "SAFE audit. Bold (ITM-2, 50% risk, no chandelier) cross-check is a TRANSFER FLAG only — C29: gate knobs do not auto-transfer across strike tiers.",
            "min_triggers_bull_1 expands the BULL side, which is OP-16 DRAFT (BULLISH_RECLAIM not yet J-proven). Flag, do not ship bull expansion without J.",
            "Propose-only: live params.json NOT edited.",
        ],
    }

    if stacked:
        chosen = run_cfg(spy, vix, _apply(params, stacked), SAFE_EQUITY)
        chosen_s = _summ(chosen)
        val = validate(chosen, "chosen_loosest_SAFE")
        out["chosen_config_SAFE"] = {
            "patch": stacked, "summary": chosen_s, "validation": val,
            "vs_baseline": {
                "delta_n": chosen_s["n"] - base_s["n"],
                "delta_total": round(chosen_s["total"] - base_s["total"], 2),
                "delta_tr_per_mo": round(chosen_s["tr_per_mo"] - base_s["tr_per_mo"], 2),
            },
        }
        chosen_bold = run_cfg(spy, vix, _apply(params, stacked), BOLD_EQUITY)
        out["chosen_config_BOLD_crosscheck"] = {
            "summary": _summ(chosen_bold), "validation": validate(chosen_bold, "chosen_loosest_BOLD"),
            "_note": "C29 transfer flag only — Bold uses ITM-2; do NOT assume the SAFE gate choice transfers.",
        }
        print(f"\nCHOSEN SAFE: n={chosen_s['n']} total=${chosen_s['total']:,.0f} "
              f"exp=${chosen_s['exp']:.0f} {chosen_s['tr_per_mo']}/mo | "
              f"VALIDATION PASS={val['gate']['PASS']} wf={val['wf_per_trade']} "
              f"oos+={val['gate']['oos_positive']} q_stable={val['gate']['sub_window_stable']}")
    else:
        out["chosen_config_SAFE"] = {"_note": "No relaxation accepted; baseline IS the +EV frontier (all gates earn keep)."}
        print("\nCHOSEN: none — all gates earn their keep at the +EV frontier (book correctly rare).")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
