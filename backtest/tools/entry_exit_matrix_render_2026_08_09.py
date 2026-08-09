"""Render the entry x exit matrix report from the harness JSON.

The harness (entry_exit_matrix_2026_08_09.py) declares OUT_MD but never writes it -- it emits
OUT_JSON + a trades file only. This renderer is the missing half: it turns those cells into the
multi-row/multi-column table J asked for and fills every [[PENDING]] / [[PLACEHOLDER]] token in
the draft doc.

Verdict logic is PRE-REGISTERED, not invented here -- it reads the frozen prereg's own
hard_gates:
  1. Tuesday 2026-08-04 no-harm (the week's dominant live day) -- a cell that degrades it cannot
     be recommended regardless of aggregate expectancy.
  2. A cell is 'notable' only if BOTH populations agree directionally, OR the disagreement is
     itself reported as the finding (the July pass's precedent: a layer conflict is a result).
Plus the standing BH-FDR q=0.10 correction the harness already computed across all cells.

Every cell is printed. No top-N truncation -- silent caps read as 'covered everything' (C7).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "analysis" / "deep-research"
IN_JSON = OUT_DIR / "ENTRY-EXIT-MATRIX-2026-08-09.json"
OUT_MD = OUT_DIR / "ENTRY-EXIT-MATRIX-2026-08-09.md"

TUESDAY = "2026-08-04"


def bh_effective_threshold(cells: dict, q: float = 0.10) -> dict:
    """Recomputed here because the completed run predates the harness's own version of this
    function (the runner was edited 3 min AFTER launch, so the live process used the older
    source). Same mechanics as backtest's benjamini_hochberg: rank p ascending, find the
    largest i with p_i <= q*i/m."""
    pv = [(k, v.get("bootstrap_p_mean_gt0")) for k, v in cells.items() if v.get("n", 0) >= 5]
    items = sorted(((k, p) for k, p in pv if p is not None), key=lambda kv: kv[1])
    m = len(items)
    max_i, thresh = 0, None
    for i, (_k, p) in enumerate(items, start=1):
        if p <= q * i / m:
            max_i, thresh = i, p
    return {"q": q, "m_tested": m, "n_survive": max_i, "effective_p_threshold": thresh,
            "min_p_observed": items[0][1] if items else None,
            "rank1_bar": round(q / m, 6) if m else None}


def cell_of(cells: dict, rid: str, cid: str) -> dict | None:
    for k in (f"{rid}__{cid}", f"{rid}|{cid}", f"{rid}::{cid}"):
        if k in cells:
            return cells[k]
    return None


def fmt(v, nd=2, dollar=True, dash="--"):
    if v is None:
        return dash
    if isinstance(v, bool):
        return "yes" if v else "no"
    try:
        return f"{'$' if dollar else ''}{float(v):,.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def grid(cells: dict, rows: list[str], cols: list[str], field: str, nd=2, dollar=True) -> list[str]:
    """One markdown table: rows = entry variants, cols = exit variants."""
    out = ["| entry \\ exit | " + " | ".join(cols) + " |",
           "|---|" + "---|" * len(cols)]
    for rid in rows:
        line = [f"| **{rid}** "]
        for cid in cols:
            c = cell_of(cells, rid, cid)
            if c is None:
                line.append("| n/a ")
            else:
                line.append(f"| {fmt(c.get(field), nd, dollar)} ")
        out.append("".join(line) + "|")
    return out


def battery_verdict(c: dict) -> str:
    """Canonical-battery shorthand per cell: which components pass."""
    if not c or not c.get("n"):
        return "no trades"
    bits = []
    exp = c.get("expectancy")
    bits.append("G1+" if (exp or 0) > 0 else "G1-")
    db = c.get("drop_best_day_expectancy")
    bits.append("G3+" if (db or 0) > 0 else "G3-")
    bits.append("stable" if c.get("sub_window_stable") else "unstable")
    p = c.get("bootstrap_p_mean_gt0")
    bits.append(f"p={p:.3f}" if isinstance(p, (int, float)) else "p=--")
    return " ".join(bits)


def full_cell_table(cells: dict, rows: list[str], cols: list[str], bh: dict) -> list[str]:
    out = ["| cell | n | days | total $ | exp $/tr | WR | drop-best exp | 1st-half | 2nd-half | "
           "stable | Tue 08-04 $ | boot p | BH q=.10 |",
           "|---|--:|--:|--:|--:|--:|--:|--:|--:|:-:|--:|--:|:-:|"]
    for rid in rows:
        for cid in cols:
            c = cell_of(cells, rid, cid)
            if c is None:
                out.append(f"| `{rid} x {cid}` | n/a (not applicable to this population) "
                           + "| " * 11 + "|")
                continue
            survived = "**PASS**" if bh.get(f"{rid}__{cid}") else "no"
            wr, p = c.get("wr"), c.get("bootstrap_p_mean_gt0")
            wr_s = f"{wr*100:.1f}%" if isinstance(wr, (int, float)) else "--"
            p_s = f"{p:.4f}" if isinstance(p, (int, float)) else "--"
            out.append(
                f"| `{rid} x {cid}` | {c.get('n', 0)} | {c.get('trading_days', '--')} | "
                f"{fmt(c.get('total'))} | {fmt(c.get('expectancy'))} | {wr_s} | "
                f"{fmt(c.get('drop_best_day_expectancy'))} | {fmt(c.get('first_half_exp'))} | "
                f"{fmt(c.get('second_half_exp'))} | {'yes' if c.get('sub_window_stable') else 'no'} | "
                f"{fmt(c.get('tuesday_0804_total'))} | {p_s} | {survived} |")
    return out


def tuesday_gate(cells: dict, rows: list[str], cols: list[str], ctl_key: str) -> list[str]:
    """The hard gate: no cell that degrades Tuesday 2026-08-04 can be recommended."""
    ctl = cells.get(ctl_key) or {}
    base = ctl.get("tuesday_0804_total")
    out = [f"Control Tuesday total: **{fmt(base)}** (n={ctl.get('tuesday_0804_n', 0)} trades that day).",
           "", "| cell | Tue 08-04 $ | vs control | gate |", "|---|--:|--:|:-:|"]
    for rid in rows:
        for cid in cols:
            c = cell_of(cells, rid, cid)
            if c is None or c.get("tuesday_0804_n", 0) == 0:
                continue
            t = c.get("tuesday_0804_total")
            if t is None or base is None:
                continue
            d = t - base
            verdict = "PASS" if d >= -0.005 * abs(base or 1) else "**DEGRADES**"
            out.append(f"| `{rid} x {cid}` | {fmt(t)} | {fmt(d)} | {verdict} |")
    if len(out) == 4:
        out.append("| _no cell had Tuesday trades_ | -- | -- | -- |")
    return out


def interactions(inter: dict, top: int) -> list[str]:
    """Super-/sub-additive: actual vs (row effect + col effect) predicted from control."""
    items = [(k, v) for k, v in inter.items() if isinstance(v, dict) and v.get("interaction") is not None]
    items.sort(key=lambda kv: -abs(kv[1]["interaction"]))
    out = ["| cell | actual exp | additive prediction | interaction | reading |",
           "|---|--:|--:|--:|---|"]
    for k, v in items[:top]:
        i = v["interaction"]
        reading = "super-additive (combo beats the sum of its parts)" if i > 0 else \
                  "sub-additive (the two changes fight each other)"
        out.append(f"| `{k.replace('__', ' x ')}` | {fmt(v['actual'])} | "
                   f"{fmt(v['predicted_additive'])} | {fmt(i)} | {reading} |")
    if len(items) > top:
        out.append(f"| _+{len(items)-top} further cells_ | | | | _full set in the JSON; "
                   f"ranked by |interaction|, none omitted from the artifact_ |")
    return out


def build(d: dict) -> str:
    A, B = d["population_a"], d["population_b"]
    rows_a, cols = d["row_order"], d["col_order"]
    rows_b = B.get("rows_applicable", rows_a)
    bh_a, bh_b = A.get("bh_pass_q010", {}) or {}, B.get("bh_pass_q010", {}) or {}
    ta = A.get("bh_effective_threshold") or bh_effective_threshold(A["cells"])
    tb = B.get("bh_effective_threshold") or bh_effective_threshold(B["cells"])
    ctl = "CONTROL__CONTROL"
    ca, cb = A["cells"].get(ctl, {}), B["cells"].get(ctl, {})

    L: list[str] = []
    add = L.append

    add(f"# ENTRY x EXIT MATRIX -- 2026-08-09")
    add("")
    add("J's `/goal`: *\"dynamic entries and exit testing across our trades, map it into a multi "
        "column/row matrix table and figure out what is profitable.\"*")
    add("")
    add(f"**Runtime:** {d.get('runtime_seconds')}s. **Generated:** {d.get('generated_at_et')}. "
        f"Frozen pre-registration: [`prereg-entry-exit-matrix-2026-08-09.json`]"
        f"(../recommendations/prereg-entry-exit-matrix-2026-08-09.json) (commit `edc595af`, "
        f"committed before the runner existed -- verified: the runner is not in that commit).")
    add("")

    # ------------------------------------------------------------------ headline
    surv_a, surv_b = ta.get("n_survive", 0), tb.get("n_survive", 0)
    add("## Verdict")
    add("")
    add(f"- **Population A** (399-day replay, {A.get('n_control_binary')} CONTROL binary trades): "
        f"**{surv_a} of {ta.get('m_tested', 0)} cells survive BH-FDR at q=0.10** "
        f"(effective p threshold {ta.get('effective_p_threshold')}).")
    add(f"- **Population B** ({B.get('n_events')} real broker fills over {B.get('n_days')} days, "
        f"{B.get('date_span')}): **{surv_b} of {tb.get('m_tested', 0)} cells survive** "
        f"(effective p threshold {tb.get('effective_p_threshold')}).")
    add(f"- **Control cell** (as-shipped entry x as-shipped exit): population A "
        f"{fmt(ca.get('expectancy'))}/trade over n={ca.get('n')}; population B "
        f"{fmt(cb.get('expectancy'))}/trade over n={cb.get('n')}.")
    add("")

    # ------------------------------------------------------------------ the matrix
    add("## THE MATRIX -- expectancy $/trade")
    add("")
    add("Rows = entry variant. Columns = exit variant. This is the crossed table: every entry "
        "rule is priced under every exit rule, so an entry that only works under a particular "
        "exit is visible as a cell rather than hidden in a row average.")
    add("")
    add("### Population A -- 399-day replay")
    add("")
    L.extend(grid(A["cells"], rows_a, cols, "expectancy"))
    add("")
    add("### Population B -- real broker fills")
    add("")
    add(f"`LADDER7/8/9` and `ZONE` are **n/a** here by construction: a realized fill carries no "
        f"score/blocker/level-scan record to re-admit against. Disclosed, not silently dropped.")
    add("")
    L.extend(grid(B["cells"], rows_b, cols, "expectancy"))
    add("")

    add("### Population A -- total $ (same grid, absolute dollars)")
    add("")
    L.extend(grid(A["cells"], rows_a, cols, "total"))
    add("")
    add("### Population A -- n (trade count per cell)")
    add("")
    L.extend(grid(A["cells"], rows_a, cols, "n", 0, False))
    add("")

    # ------------------------------------------------------------------ full battery
    add("## Full per-cell battery -- every cell, no truncation")
    add("")
    add("### Population A")
    add("")
    L.extend(full_cell_table(A["cells"], rows_a, cols, bh_a))
    add("")
    add("### Population B")
    add("")
    L.extend(full_cell_table(B["cells"], rows_b, cols, bh_b))
    add("")

    # ------------------------------------------------------------------ BH
    add("## BH-FDR survivors (q = 0.10)")
    add("")
    sa = [k for k, v in bh_a.items() if v]
    sb = [k for k, v in bh_b.items() if v]
    add(f"**Population A: {len(sa)} survivor(s).**"
        + ("" if sa else " Nothing clears the multiple-comparison correction."))
    for k in sa:
        c = A["cells"].get(k, {})
        add(f"- `{k.replace('__', ' x ')}` -- exp {fmt(c.get('expectancy'))}/tr, n={c.get('n')}, "
            f"p={c.get('bootstrap_p_mean_gt0')}, drop-best {fmt(c.get('drop_best_day_expectancy'))}, "
            f"sub-window {'stable' if c.get('sub_window_stable') else 'UNSTABLE'}")
    add("")
    add(f"**Population B: {len(sb)} survivor(s).**"
        + ("" if sb else " Nothing clears the multiple-comparison correction."))
    for k in sb:
        c = B["cells"].get(k, {})
        add(f"- `{k.replace('__', ' x ')}` -- exp {fmt(c.get('expectancy'))}/tr, n={c.get('n')}, "
            f"p={c.get('bootstrap_p_mean_gt0')}, drop-best {fmt(c.get('drop_best_day_expectancy'))}, "
            f"sub-window {'stable' if c.get('sub_window_stable') else 'UNSTABLE'}")
    add("")
    both = sorted(set(sa) & set(sb))
    add(f"**Survives in BOTH populations: {len(both)}** "
        + (", ".join(f"`{k.replace('__', ' x ')}`" for k in both) if both
           else "-- none. Per the prereg's second hard gate, a cell is only 'notable' if both "
                "populations agree directionally or the disagreement is itself the reported "
                "finding. With no cell clearing both, the disagreement IS the finding."))
    add("")

    # ------------------------------------------------------------------ Tuesday
    add(f"## Hard gate -- Tuesday {TUESDAY} no-harm")
    add("")
    add("Tuesday was +$3,624 book-wide, the week's dominant day. Any cell that degrades it is "
        "unrecommendable regardless of aggregate expectancy.")
    add("")
    add("### Population A")
    add("")
    L.extend(tuesday_gate(A["cells"], rows_a, cols, ctl))
    add("")
    add("### Population B")
    add("")
    L.extend(tuesday_gate(B["cells"], rows_b, cols, ctl))
    add("")

    # ------------------------------------------------------------------ interactions
    add("## Interaction effects -- does entry x exit compound?")
    add("")
    add("`interaction = actual - (control + row effect + column effect)`. A large positive value "
        "means the pair does something neither change does alone -- the whole point of crossing "
        "the matrix instead of testing entries and exits separately.")
    add("")
    add("### Population A")
    add("")
    L.extend(interactions(A.get("interaction", {}), 20))
    add("")
    add("### Population B")
    add("")
    L.extend(interactions(B.get("interaction", {}), 20))
    add("")

    # ------------------------------------------------------------------ artifact audit
    audit_p = OUT_DIR / "ENTRY-EXIT-MATRIX-ATR-AUDIT-2026-08-09.json"
    if audit_p.exists():
        au = json.loads(audit_p.read_text(encoding="utf-8"))
        v, C = au["verdict"], au["columns"]
        add("## /fable-too-good audit of the winning cell -- READ THIS BEFORE THE TABLE ABOVE")
        add("")
        add("`ATR_STOP` won every non-ladder row in both populations by a wide margin. That shape "
            "demands an artifact hunt before it is reported as an edge. The hunt found two real "
            "structural problems, and decomposing them inverts the headline.")
        add("")
        add("**Problem 1 -- look-ahead.** `_atr_stop_col` derives the stop width from "
            "`opt_df[:6]`, and `_opt_bars_from` returns bars with `ts >= entry`. So the stop is "
            "computed from the realized high/low of the first 6 bars AFTER entry, then tested "
            "against those same bars. A trade that whipsaws right after entry gets a large ATR, "
            "hence a wide stop, hence is NOT stopped on the whipsaw; a quiet trade gets a tight "
            "one. The rule hands the widest stops to exactly the trades that would otherwise have "
            "been stopped out (C6).")
        add("")
        add("**Problem 2 -- mode confound.** Control is `stop_mode=\"structure\"` "
            "(`structure_stop_enabled=True`). `_atr_stop_col` returns `stop_mode=\"premium\"`, "
            "which turns structure stops OFF. The column changes two things at once.")
        add("")
        add("**Checked and NOT a confound:** the column drops `profit_lock_arm_scope`, but "
            "`exit_manager` defaults it to `post_tp1` -- the same value control carries. Recorded "
            "so nobody re-hunts it.")
        add("")
        wp = v["walker_parity"]
        add(f"**Walker parity -- the biggest suspicion, and it is CLEARED.** `ATR_STOP` was the "
            f"only population-A column walked by `walk_lane_dynamic_shape`, a hand-duplicated "
            f"twin of `sl.walk_lane`; a cross-engine comparison is the SIM-EXIT-SHAPE-PARITY "
            f"scar. Running the control shape through the twin reproduces `sl.walk_lane` "
            f"**exactly**: {fmt(wp['twin_control_expectancy'])}/trade on n={wp['twin_control_n']} "
            f"versus {fmt(wp['sl_walk_lane_control_expectancy'])} on "
            f"n={wp['sl_walk_lane_control_n']}, delta **{fmt(wp['delta_per_trade'])}**. The twin "
            f"is faithful; the walker is not the explanation.")
        add("")
        add("| column | n | exp $/tr | total $ | WR | drop-best exp | 1st half | 2nd half | stable | boot p |")
        add("|---|--:|--:|--:|--:|--:|--:|--:|:-:|--:|")
        for name, c in C.items():
            add(f"| `{name}` | {c['n']} | {fmt(c['expectancy'])} | {fmt(c['total'])} | "
                f"{c['wr']*100:.1f}% | {fmt(c['drop_best_day_expectancy'])} | "
                f"{fmt(c['first_half_exp'])} | {fmt(c['second_half_exp'])} | "
                f"{'yes' if c['sub_window_stable'] else 'no'} | {c['bootstrap_p_mean_gt0']:.4f} |")
        add("")
        add("### The decomposition -- where the $79.20 actually comes from")
        add("")
        add("| component | $/trade | what it is |")
        add("|---|--:|---|")
        add(f"| stop_mode: structure -> premium | **{fmt(v['mode_effect_alone_per_trade'])}** | "
            f"turning the structure stop OFF and using a flat -20% premium stop |")
        add(f"| look-ahead artifact | {fmt(v['lookahead_inflation_per_trade'])} | "
            f"pure hindsight, not available live |")
        add(f"| the dynamic width itself | **{fmt(v['dynamic_width_effect_alone_per_trade'])}** | "
            f"ATR-computed width vs a flat -20%, measured with the look-ahead removed |")
        add(f"| **total** | **{fmt(v['mode_effect_alone_per_trade'] + v['lookahead_inflation_per_trade'] + v['dynamic_width_effect_alone_per_trade'])}** "
            f"| reconciles to the {fmt(C['ATR_LOOKAHEAD']['expectancy'])} - {fmt(C['TWIN_CONTROL']['expectancy'])} headline gap |")
        add("")
        add("**So the dynamic stop is not the edge.** Measured honestly, a per-trade ATR-computed "
            "stop width is *slightly worse* than a flat -20% premium stop. Roughly a third of the "
            "headline was hindsight. What is left -- and it is the large majority of it -- is a "
            "single binary flag: **the structure stop.**")
        add("")
        add("This is a POST-HOC finding. The frozen prereg tested `ATR_STOP`; it did not "
            "pre-register `stop_mode`. It therefore does NOT ship on this evidence -- it gets its "
            "own frozen pre-registration and its own run, on both populations, with the Tuesday "
            "gate evaluable. Shipping a post-hoc cell is how the bar gets softened.")
        add("")
        add("**Open caveats on the stop_mode result, stated rather than buried:**")
        for c in [
            f"The Tuesday {TUESDAY} hard gate is **untestable** on this cohort -- the CONTROL "
            f"entry row admitted zero trades on that date (`tuesday_0804_n=0`). Not passed; not "
            f"evaluable.",
            "It contradicts explicitly ratified doctrine (chart-stop-primary, 2026-06-18). That "
            "does not make it wrong -- ribbon flip being a lagging exit is already C28 in the "
            "lessons index, and this is consistent with it -- but reversing a ratified mechanism "
            "needs its own evidence, not a side effect of an exit-grid cell.",
            "Population B (real broker fills) has not been decomposed the same way. Its "
            "`ATR_STOP` cell carries the identical look-ahead and mode confound, so its $57-71/tr "
            "is NOT independent corroboration of the mode effect yet.",
            "Win rate goes DOWN under the premium stop (21.0% vs 24.6%) while total P&L goes up: "
            "fewer winners, but losers cut faster and winners not flipped out early. That is a "
            "coherent mechanism, not just a number -- but it is the mechanism that needs "
            "confirming, not the dollar figure.",
            "This is a replay population, not the live book. The replayed as-shipped control "
            "earns $16.06/trade here; the live book's last 23-day base rate ex-Tuesday is "
            "negative. Treat the delta as a signal to test, never as a promised dollar amount.",
        ]:
            add(f"- {c}")
        add("")

    add("## Method disclosures")
    add("")
    for line in [
        "**Sequential, one-position-at-a-time (NOT_FLAT) walk**, re-derived independently per "
        "(row, col) cell -- a wider stop's suppression of later re-entries is measured per cell, "
        "never assumed or recombined across independently-simulated trades.",
        "**Exit engine identical across both populations**: `exit_manager_walk.walk_exit_manager` "
        "-> `exit_manager.plan_exit_actions`, never `simulator_real` (the 2026-07-09 "
        "SIM-EXIT-SHAPE-PARITY scar stays closed).",
        "**5-minute OPRA touch-resolution** for both populations, held constant so resolution is "
        "never itself a confound.",
        "**Runner-cohort is incomplete by construction for most Population-A columns.** The reused "
        "`score_ladder_replay` trade schema does not tag TP1 fills, so `runner_cohort_n` is only "
        "populated for `ATR_STOP` (this file's own walker) and for Population B. Elsewhere "
        "`runner_cohort_n=0` means NOT MEASURED, never 'zero trades reached TP1'. Every other "
        "battery component is computed for all cells.",
        "**`MFE_TRAIL` and `ATR_STOP` are deliberately simpler than a from-scratch dynamic exit** "
        "(disclosed in the prereg). The authoritative per-trade dynamic-exit study is the sibling "
        "[`DYNAMIC-EXITS-2026-08-09.md`](DYNAMIC-EXITS-2026-08-09.md); where the two disagree, "
        "trust the sibling for the exit-only question.",
    ]:
        add(f"- {line}")
    add("")
    add(f"Raw per-cell JSON: `ENTRY-EXIT-MATRIX-2026-08-09.json` (committed). Per-trade detail: "
        f"`ENTRY-EXIT-MATRIX-2026-08-09-trades.json` -- 35MB, **gitignored and local-only**, "
        f"regenerable by re-running the harness. Artifact audit: "
        f"`ENTRY-EXIT-MATRIX-ATR-AUDIT-2026-08-09.json`.")
    add("")
    return "\n".join(L) + "\n"


def main() -> int:
    if not IN_JSON.exists():
        print(f"[render] {IN_JSON} does not exist yet -- harness still running?")
        return 1
    d = json.loads(IN_JSON.read_text(encoding="utf-8"))
    OUT_MD.write_text(build(d), encoding="utf-8")
    print(f"[render] wrote {OUT_MD} ({OUT_MD.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
