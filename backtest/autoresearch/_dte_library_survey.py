"""DTE-LIBRARY-SURVEY (Angle B) — does the dead 0DTE directional library RESURRECT at 1-2DTE?

Post-processor over the per-family DTE-expansion sim JSONs (analysis/recommendations/
dte-expansion-{family}.json, produced by _dte_expansion_sim.py with the byte-for-byte
detectors). For each dead family (momentum_morning, orb_continuation, power_hour,
vwap_pullback) + the vwap_continuation control, per DTE (0/1/2):

  * report OOS per-trade, n, the FULL gate result, gap accounting;
  * apply the two gates the sim summary can't carry alone:
      GATE 7 random-entry NULL (L172) — DTE-aware: random RTH entries on the SAME days,
              SAME side mix, SAME strike+stop+DTE, run through the sim's OWN
              simulate_dte_trade (holds overnight identically). Beat null MAX + drop-top5
              beats null MEAN.
      GATE 8 no-truncation (L171) — same-strike chart-stop-only cell must not be negative
              while the chosen tight-stop cell is positive.
  * for any cell that is OOS-POSITIVE at 1-2DTE but FAILS L173 (gate 9 OOS-alone drop-top5),
    attempt a DE-CONCENTRATION (persistence / magnitude / regime filters) and report
    honestly whether it survives.

VERDICT: RESURRECT count (0DTE-dead -> 1-2DTE OOS-positive) and SHIPPABLE count (clears
ALL gates incl L173 with n>=20). LIBRARY_REOPENS / PARTIAL_RESURRECTION / ALL_L173_FRAGILE / DEAD.

Pure Python, $0. No live orders. No edits to detectors/params/risk_gate/orchestrator/heartbeat.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_dte_library_survey.py
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

from lib.truncation_guard import is_truncation_artifact, TIGHT_STOP_THRESHOLD  # noqa: E402

import _dte_expansion_sim as sim  # noqa: E402

REC = ROOT / "analysis" / "recommendations"
OUT_MD = REC / "DTE-LIBRARY-SURVEY.md"
OUT_JSON = REC / "DTE-LIBRARY-SURVEY.json"

DEAD_FAMILIES = ["momentum_morning", "orb_continuation", "power_hour", "vwap_pullback"]
CONTROL = "vwap_continuation"
ALL_FAMILIES = [CONTROL] + DEAD_FAMILIES

OOS_YEAR = sim.OOS_YEAR
NULL_SEEDS = 20
ENTRY_GATE = (dt.time(9, 35), dt.time(15, 30))  # causal RTH window for the null draws


# ─────────────────────────────────────────────────────────────────────────────
# GATE 7 — DTE-aware random-entry null. Reuse the sim's OWN simulate_dte_trade so
# the null holds overnight + settles at expiry exactly like the signal cell. The
# signal is isolated from the exit STRUCTURE (C3/L58) by drawing entry bars at
# RANDOM RTH positions on the SAME entry days, with the SAME side mix.
# ─────────────────────────────────────────────────────────────────────────────
def _rth_idxs_for_day(spy, day: dt.date) -> list[int]:
    sub = spy[(spy["date"] == day) & (spy["t"] >= ENTRY_GATE[0]) & (spy["t"] <= ENTRY_GATE[1])]
    return [int(i) for i in sub.index.tolist()]


def dte_null(cell_rows, spy, day_open_close, dte, strike_offset, premium_stop_pct,
             seeds: int = NULL_SEEDS) -> dict:
    """Random-entry null matched to the cell. cell_rows = the signal cell's recorded rows
    (for n, side mix, the entry-day set). Draws random RTH bars on those SAME days, builds
    a Signal at each, and runs simulate_dte_trade with the cell's strike/stop/DTE."""
    if not cell_rows:
        return {"per_trade_mean": 0.0, "per_trade_max": 0.0, "per_trade_min": 0.0, "n_drawn": 0}
    days = sorted({dt.date.fromisoformat(r["date"]) for r in cell_rows})
    n_call = sum(1 for r in cell_rows if r["side"] == "C")
    n_put = sum(1 for r in cell_rows if r["side"] == "P")
    n_sig = len(cell_rows)
    # eligible (day -> rth idxs) computed once
    day_idxs = {d: _rth_idxs_for_day(spy, d) for d in days}
    day_idxs = {d: ix for d, ix in day_idxs.items() if ix}
    elig_days = list(day_idxs)
    if not elig_days:
        return {"per_trade_mean": 0.0, "per_trade_max": 0.0, "per_trade_min": 0.0, "n_drawn": 0}

    per_trades: list[float] = []
    for seed in range(seeds):
        rng = random.Random(seed)
        sides = ["C"] * n_call + ["P"] * n_put
        if len(sides) < n_sig:
            sides += ["C" if n_call >= n_put else "P"] * (n_sig - len(sides))
        rng.shuffle(sides)
        pnl = 0.0
        nn = 0
        draw_days = [rng.choice(elig_days) for _ in range(n_sig)]
        for k in range(n_sig):
            d = draw_days[k]
            side = sides[k]
            bidx = rng.choice(day_idxs[d])
            bar = spy.iloc[bidx]
            spot = float(bar["close"])
            atm = sim._strike_from_spot(spot)
            target = atm - strike_offset if side == "P" else atm + strike_offset
            res = sim._nearest_cached_strike_dte(d, target, side, dte)
            if res is None:
                continue
            strike, expiry = res
            # neutral chart stop = current bar extreme against the trade (swing-style)
            stop_level = float(bar["low"]) if side == "C" else float(bar["high"])
            sg = sim.Signal(bar_idx=bidx, side=side, stop_level=stop_level, note="random_null")
            fill = sim.simulate_dte_trade(sg, spy, {}, day_open_close, dte,
                                          strike=strike, expiry=expiry, side=side,
                                          qty=sim.QTY, premium_stop_pct=premium_stop_pct)
            if fill is None:
                continue
            pnl += fill.dollar_pnl
            nn += 1
        per_trades.append(pnl / nn if nn else 0.0)
    return {
        "seeds": seeds,
        "per_trade_mean": round(float(np.mean(per_trades)), 2),
        "per_trade_max": round(float(max(per_trades)), 2),
        "per_trade_min": round(float(min(per_trades)), 2),
        "n_drawn": n_sig,
    }


def _cell_oos_per_trade(cell) -> Optional[float]:
    return cell["metrics"].get("oos_exp")


def _cell_oos_drop_top5(cell):
    return cell["metrics"].get("oos_drop_top5"), cell["metrics"].get("oos_drop_top5_evaluable")


def _drop_top5_full(cell):
    return cell["metrics"].get("drop_top5_full")


# ─────────────────────────────────────────────────────────────────────────────
# DE-CONCENTRATION attempts (the persistence / magnitude / regime fixes). Applied
# only to cells that are OOS-POSITIVE but FAIL the L173 OOS-alone drop-top5 gate.
# Each fix is a row-subset filter; we recompute OOS per-trade + OOS-drop-top5 on the
# kept subset and report whether L173 now passes WITHOUT going OOS-negative or n<20.
# Honest: many won't de-concentrate (the lift is a few fat days, removing them kills it).
# ─────────────────────────────────────────────────────────────────────────────
def _oos_metrics(rows) -> tuple[Optional[float], Optional[float], int]:
    oos = [r for r in rows if int(r["date"][:4]) == OOS_YEAR]
    if not oos:
        return None, None, 0
    pt = sum(r["dollar_pnl"] for r in oos) / len(oos)
    by_day = defaultdict(list)
    for r in oos:
        by_day[r["date"]].append(r["dollar_pnl"])
    if len(by_day) <= 5:
        return round(pt, 2), None, len(oos)
    day_tot = sorted(by_day.items(), key=lambda kv: sum(kv[1]), reverse=True)
    kept = [p for _, pnls in day_tot[5:] for p in pnls]
    dt5 = (sum(kept) / len(kept)) if kept else None
    return round(pt, 2), (round(dt5, 2) if dt5 is not None else None), len(oos)


MIN_OOS_FLOOR = sim.MIN_OOS_TO_DROP_TOP5 + sim.BAR_N  # 25: robust drop-5 needs real n


def _full_subset_metrics(rows) -> dict:
    """OOS per-trade, OOS-drop-top5, posQ, IS-first-half, full-drop-top5 on a row subset.
    Used so a de-concentration candidate must re-clear the FULL bar, not just OOS-dropT5
    (a side cherry-pick that only clears OOS-dropT5 is survivorship, C24/L140)."""
    oos_pt, oos_dt5, oosn = _oos_metrics(rows)
    # full-sample drop-top5
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["date"]].append(r["dollar_pnl"])
    day_tot = sorted(by_day.items(), key=lambda kv: sum(kv[1]), reverse=True)
    kept_full = [p for _, pnls in day_tot[5:] for p in pnls]
    full_dt5 = (sum(kept_full) / len(kept_full)) if kept_full else None
    # positive quarters
    byq = defaultdict(float)
    for r in rows:
        y, m, _ = r["date"].split("-")
        byq[f"{y}Q{(int(m) - 1) // 3 + 1}"] += r["dollar_pnl"]
    posq = sum(1 for v in byq.values() if v > 0)
    # IS-2025 first half
    fh = [r["dollar_pnl"] for r in rows if r["date"][:4] == "2025" and r["date"][5:7] <= "06"]
    is_fh = (sum(fh) / len(fh)) if fh else None
    return {"oos_per_trade": oos_pt, "oos_drop_top5": oos_dt5, "oos_n": oosn,
            "full_drop_top5": round(full_dt5, 2) if full_dt5 is not None else None,
            "positive_quarters_n": posq, "n_quarters": len(byq),
            "is_first_half": round(is_fh, 2) if is_fh is not None else None,
            "n": len(rows)}


def deconcentrate(cell) -> dict:
    """Honest, CAUSAL de-concentration of an L173-fragile OOS-positive cell.

    The lift on these flips lives in a few fat OOS days; the test is whether a CAUSAL
    structural sub-rule (drop the persistence-failing days, or a side split) removes the
    concentration WITHOUT going OOS-negative or n<20 — AND the survivor must re-clear the
    FULL bar (posQ>=4, full-drop-top5>0, IS-first-half>0, OOS-drop-top5>0), not merely the
    OOS-drop-top5 line (a single-side cherry-pick that only clears OOS-dropT5 is C24/L140
    survivorship, not a real fix). NO outcome-based filtering (no pct_return floor — that is
    circular look-ahead, C6). Robustness floor: oos_n strictly > 5+BAR_N so the drop-5 is
    not evaluated on a knife-edge ~20-obs set."""
    rows = cell.get("rows", [])
    attempts = []

    # FIX A — PERSISTENCE: drop the single biggest OOS day. If the edge survives losing its
    #   one fat tail it is not a one-day artifact; if it collapses it is.
    oos = [r for r in rows if int(r["date"][:4]) == OOS_YEAR]
    if oos:
        by_day = defaultdict(float)
        for r in oos:
            by_day[r["date"]] += r["dollar_pnl"]
        worst = max(by_day, key=by_day.get)
        attempts.append(("drop_top1_oos_day",
                         _full_subset_metrics([r for r in rows if r["date"] != worst])))

    # FIX B — SIDE SPLIT: keep only one side (concentration can live on one side's fat days).
    for side in ("C", "P"):
        sub = [r for r in rows if r["side"] == side]
        if len(sub) >= sim.BAR_N:
            attempts.append((f"side={side}_only", _full_subset_metrics(sub)))

    ROBUST_OOS_FLOOR = MIN_OOS_FLOOR  # strictly > 5 + BAR_N to avoid knife-edge drop-5
    winners = []
    for name, m in attempts:
        full_clears = (
            m["oos_per_trade"] is not None and m["oos_per_trade"] > 0
            and m["oos_drop_top5"] is not None and m["oos_drop_top5"] > 0
            and m["full_drop_top5"] is not None and m["full_drop_top5"] > 0
            and m["positive_quarters_n"] >= sim.BAR_POS_Q
            and m["is_first_half"] is not None and m["is_first_half"] > 0
            and m["n"] >= sim.BAR_N
            and m["oos_n"] > ROBUST_OOS_FLOOR
        )
        if full_clears:
            winners.append((name, m))
    winners.sort(key=lambda x: x[1]["oos_drop_top5"], reverse=True)
    return {
        "attempts": [{"fix": n, **m} for n, m in attempts],
        "deconcentrated": bool(winners),
        "winner": (None if not winners else {"fix": winners[0][0], **winners[0][1]}),
    }


# ─────────────────────────────────────────────────────────────────────────────
def best_cell_for_dte(fam_data, dte: int) -> Optional[dict]:
    """Pick the representative cell for a (family,DTE): prefer a structural-clearing cell
    with the highest OOS per-trade; else the highest-OOS cell with n>=20 (to characterise
    the sign even when it fails gates)."""
    cells = fam_data["by_dte"][str(dte)]["cells"]
    valid = [c for c in cells if c["metrics"].get("n", 0) >= sim.BAR_N]
    if not valid:
        valid = [c for c in cells if c["metrics"].get("n", 0) > 0]
    if not valid:
        return None
    clearing = [c for c in valid if c["clears_bar"]]
    pool = clearing if clearing else valid
    pool.sort(key=lambda c: (c["metrics"].get("oos_exp") or -1e9), reverse=True)
    return pool[0]


def main() -> int:
    print("[survey] loading SPY+VIX for the DTE null ...", flush=True)
    spy, vix = sim._load_spy_vix()
    day_open_close = sim._spy_day_open_close(spy)
    for dte in (1, 2):
        sim._build_expiry_index(dte)

    fam_json = {}
    for fam in ALL_FAMILIES:
        p = REC / f"dte-expansion-{fam}.json"
        if not p.exists():
            print(f"[survey] MISSING {p} — run _dte_expansion_sim.py --family {fam} first")
            return 1
        fam_json[fam] = json.loads(p.read_text())

    survey = {"run_date": dt.date.today().isoformat(),
              "window": fam_json[CONTROL]["window"], "families": {}}

    for fam in ALL_FAMILIES:
        fd = fam_json[fam]
        fam_out = {"n_signals": fd["n_signals"], "by_dte": {}}
        # 0DTE sign reference (is the family dead at 0DTE?)
        for dte in (0, 1, 2):
            cell = best_cell_for_dte(fd, dte)
            if cell is None:
                fam_out["by_dte"][str(dte)] = {"n": 0, "note": "no fillable cell"}
                continue
            m = cell["metrics"]
            so = cell["strike_offset"]
            ps = cell["premium_stop_pct"]
            # GATE 8 no-truncation: same-strike chart-stop-only (-0.99) cell per-trade
            chart_cell = next((c for c in fd["by_dte"][str(dte)]["cells"]
                               if c["strike_offset"] == so and c["premium_stop_pct"] == -0.99), None)
            chart_pt = chart_cell["metrics"].get("exp_dollar") if chart_cell else None
            trunc_artifact = is_truncation_artifact(
                best_per_trade=m.get("exp_dollar"),
                chart_stop_only_per_trade=chart_pt,
                best_premium_stop_pct=ps,
            )
            # GATE 7 null — only worth running on cells that are at least OOS-positive
            null = None
            null_pass = None
            if (m.get("oos_exp") or -1) > 0 and cell["clears_bar"]:
                null = dte_null(cell.get("rows", []), spy, day_open_close, dte, so, ps)
                dt5_full = _drop_top5_full(cell)
                beats_max = m.get("exp_dollar") is not None and m["exp_dollar"] > null["per_trade_max"]
                drop_beats_mean = dt5_full is not None and dt5_full > null["per_trade_mean"]
                null_pass = bool(beats_max and drop_beats_mean)

            oos_dt5, oos_dt5_eval = _cell_oos_drop_top5(cell)
            l173_pass = bool(oos_dt5_eval and oos_dt5 is not None and oos_dt5 > 0)

            # full ALL-GATE verdict (structural gates from clears_bar + gate7 + gate8)
            all_gates = bool(cell["clears_bar"] and (null_pass is True) and (not trunc_artifact))

            entry = {
                "strike_tier": cell["strike_tier"], "strike_offset": so, "premium_stop_pct": ps,
                "n": m.get("n"), "oos_n": m.get("oos_n"),
                "oos_per_trade": m.get("oos_exp"), "exp_per_trade": m.get("exp_dollar"),
                "is_first_half": m.get("is_first_half_exp"),
                "positive_quarters": m.get("positive_quarters"),
                "top5_day_pct": m.get("top5_day_pct"),
                "drop_top5_full": _drop_top5_full(cell),
                "oos_drop_top5": oos_dt5, "oos_drop_top5_evaluable": oos_dt5_eval,
                "L173_pass": l173_pass,
                "risk_adj_exp_over_std": m.get("risk_adj_exp"),
                "structural_gates_pass": cell["clears_bar"],
                "structural_fails": cell["clears_bar_fails"],
                "gate7_null": null, "gate7_null_pass": null_pass,
                "gate8_truncation_artifact": trunc_artifact,
                "all_gates_pass": all_gates,
                "overnight": m.get("overnight"),
                "gap_contribution_dollar": m.get("gap_contribution_dollar"),
            }
            # de-concentration attempt for OOS-positive but L173-fragile cells at 1-2DTE
            if dte in (1, 2) and (m.get("oos_exp") or -1) > 0 and not l173_pass:
                entry["deconcentration"] = deconcentrate(cell)
            fam_out["by_dte"][str(dte)] = entry
            print(f"  {fam:18s} DTE={dte} {cell['strike_tier']:>5} stop={ps:>6} "
                  f"n={m.get('n')} oos/tr=${m.get('oos_exp')} oos_dropT5={oos_dt5} "
                  f"L173={'P' if l173_pass else 'F'} struct={'P' if cell['clears_bar'] else 'F'} "
                  f"null={null_pass} trunc={'BAD' if trunc_artifact else 'ok'} "
                  f"ALL={'SHIP' if all_gates and l173_pass else '-'}", flush=True)

        # resurrection: 0DTE OOS<=0 (or struct-fail) -> 1or2 DTE OOS>0
        d0 = fam_out["by_dte"].get("0", {})
        d0_oos = d0.get("oos_per_trade")
        d0_dead = (d0_oos is None) or (d0_oos <= 0) or (not d0.get("structural_gates_pass"))
        flips_positive = any(
            (fam_out["by_dte"].get(str(d), {}).get("oos_per_trade") or -1) > 0
            for d in (1, 2))
        shippable = any(
            fam_out["by_dte"].get(str(d), {}).get("all_gates_pass") and
            fam_out["by_dte"].get(str(d), {}).get("L173_pass") and
            (fam_out["by_dte"].get(str(d), {}).get("n") or 0) >= sim.BAR_N
            for d in (1, 2))
        fam_out["resurrects"] = bool(d0_dead and flips_positive)
        fam_out["shippable_1_2dte"] = bool(shippable)
        survey["families"][fam] = fam_out

    # ── VERDICT ──────────────────────────────────────────────────────────────
    dead = [f for f in DEAD_FAMILIES]
    resurrected = [f for f in dead if survey["families"][f]["resurrects"]]
    shippable = [f for f in dead if survey["families"][f]["shippable_1_2dte"]]
    if len(shippable) >= 2:
        verdict = "LIBRARY_REOPENS"
    elif resurrected:
        verdict = "PARTIAL_RESURRECTION"
    elif any((survey["families"][f]["by_dte"].get(str(d), {}).get("oos_per_trade") or -1) > 0
             for f in dead for d in (1, 2)):
        verdict = "ALL_L173_FRAGILE"
    else:
        verdict = "DEAD"
    survey["verdict"] = verdict
    survey["resurrected_families"] = resurrected
    survey["shippable_families"] = shippable

    OUT_JSON.write_text(json.dumps(survey, indent=2, default=str), encoding="utf-8")
    _write_md(survey)
    print(f"\n[survey] VERDICT={verdict} resurrected={resurrected} shippable={shippable}")
    print(f"[survey] wrote {OUT_JSON} + {OUT_MD}")
    return 0


def _fmt(v):
    return "-" if v is None else (f"${v}" if isinstance(v, (int, float)) else str(v))


def _write_md(s: dict) -> None:
    L = []
    L.append("# DTE-LIBRARY-SURVEY — does the dead 0DTE directional library reopen at 1-2DTE? (Angle B)")
    L.append("")
    L.append(f"_Run {s['run_date']} • window {s['window']} • SUNDAY/markets-closed • $0 compute • "
             "byte-for-byte detectors, no edits to detectors/params/risk_gate/orchestrator/heartbeat._")
    L.append("")
    L.append(f"## VERDICT: **{s['verdict']}**")
    L.append("")
    L.append(f"- Dead families tested: {', '.join(DEAD_FAMILIES)} (+ {CONTROL} as live control)")
    L.append(f"- RESURRECTED (0DTE-dead -> 1-2DTE OOS-positive): "
             f"**{len(s['resurrected_families'])}** {s['resurrected_families']}")
    L.append(f"- SHIPPABLE (clears ALL gates incl L173, n>=20, at 1-2DTE): "
             f"**{len(s['shippable_families'])}** {s['shippable_families']}")
    L.append("")
    L.append("Gate legend: structural = OOS>0 + posQ>=4 + top5<200% + n>=20 + full-drop-top5>0 "
             "+ IS-first-half>0 + OOS-alone-drop-top5>0 (L173); gate7 = beats random-entry DTE null "
             "(L172); gate8 = not a tight-stop truncation artifact (L171). ALL = every gate incl L173.")
    L.append("")
    for fam in ALL_FAMILIES:
        fd = s["families"][fam]
        tag = "CONTROL (already LIVE)" if fam == CONTROL else (
            "RESURRECTS" if fd["resurrects"] else "no resurrection")
        ship = " — SHIPPABLE at 1-2DTE" if fd["shippable_1_2dte"] else ""
        L.append(f"## {fam} — {tag}{ship}")
        L.append(f"_signals: {fd['n_signals']}_")
        L.append("")
        L.append("| DTE | tier/stop | n | OOS/tr | OOS-dropT5 (L173) | posQ | top5% | "
                 "IS-1H | risk-adj exp/std | struct | gate7 null | gate8 trunc | gap$ | held% | ALL |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for dte in ("0", "1", "2"):
            e = fd["by_dte"].get(dte, {})
            if not e or e.get("n", 0) == 0:
                L.append(f"| {dte} | - | 0 | - | - | - | - | - | - | - | - | - | - | - | - |")
                continue
            ov = e.get("overnight") or {}
            allp = "**SHIP**" if (e.get("all_gates_pass") and e.get("L173_pass")) else "-"
            L.append(
                f"| {dte} | {e.get('strike_tier')}/{e.get('premium_stop_pct')} | {e.get('n')} | "
                f"{_fmt(e.get('oos_per_trade'))} | "
                f"{_fmt(e.get('oos_drop_top5'))}{'' if e.get('oos_drop_top5_evaluable') else ' (uneval)'} "
                f"{'PASS' if e.get('L173_pass') else 'FAIL'} | "
                f"{e.get('positive_quarters')} | {e.get('top5_day_pct')} | "
                f"{_fmt(e.get('is_first_half'))} | {_fmt(e.get('risk_adj_exp_over_std'))} | "
                f"{'P' if e.get('structural_gates_pass') else 'F'} | "
                f"{e.get('gate7_null_pass')} | {'BAD' if e.get('gate8_truncation_artifact') else 'ok'} | "
                f"{_fmt(e.get('gap_contribution_dollar'))} | {ov.get('held_overnight_pct')} | {allp} |")
        # structural fails detail + de-concentration
        for dte in ("0", "1", "2"):
            e = fd["by_dte"].get(dte, {})
            if e.get("structural_fails"):
                L.append(f"")
                L.append(f"- DTE={dte} structural fails: {', '.join(e['structural_fails'])}")
            dc = e.get("deconcentration")
            if dc:
                res = "SUCCEEDED" if dc["deconcentrated"] else "FAILED (stays L173-fragile)"
                L.append(f"- DTE={dte} **de-concentration {res}** (must re-clear FULL bar, "
                         f"causal only — no outcome-based filtering):")
                for a in dc["attempts"]:
                    L.append(f"    - {a['fix']}: n={a.get('n')} oos_n={a.get('oos_n')} "
                             f"oos/tr={_fmt(a.get('oos_per_trade'))} oos-dropT5={_fmt(a.get('oos_drop_top5'))} "
                             f"full-dropT5={_fmt(a.get('full_drop_top5'))} posQ={a.get('positive_quarters_n')} "
                             f"IS1H={_fmt(a.get('is_first_half'))}")
                if dc["winner"]:
                    w = dc["winner"]
                    L.append(f"    - WINNER: {w['fix']} -> oos/tr={_fmt(w.get('oos_per_trade'))} "
                             f"oos-dropT5={_fmt(w.get('oos_drop_top5'))} (n={w.get('n')}, oos_n={w.get('oos_n')})")
        L.append("")
    L.append("## Honest caveats")
    L.append("")
    L.append("- **Overnight gap risk is modeled, not assumed away.** Held-overnight trades settle at "
             "expiry intrinsic on real SPY closes; a chart stop can GAP THROUGH overnight "
             "(reason GAP_THROUGH_STOP). The `gap$` column is the dollar contribution of the "
             "close-to-open gap to held trades — small/zero means the lift is theta-driven, not gap-driven.")
    L.append("- **Lower gamma at 1-2DTE inflates per-trade variance** (risk-adj exp/std column). A "
             "family can add OOS dollars yet have WORSE risk-adjusted return — that is a risk-up "
             "tradeoff (J's call per L175), not a clean win.")
    L.append("- **L173 is the decisive de-concentration gate.** A cell can be OOS-positive and still "
             "fail because the OOS lift lives in <=5 fat days; removing them turns it negative. Many "
             "1-2DTE flips are exactly this (gap_fade was the canonical example).")
    L.append("- Settlement uses real SPY closes; the DTE cache holds entry-day option bars only, so "
             "mid-life option marks are never synthesised — terminal value is pure intrinsic.")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
