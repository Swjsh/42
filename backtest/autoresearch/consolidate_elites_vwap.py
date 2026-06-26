"""Consolidate the vwap_continuation funnel P4 elites into a DEPLOYABLE shortlist.

The vwap analog of ``consolidate_elites.py``. The funnel produces many "PASS-P4 elite"
rows, but they are NOT independent strategies — they are exit-knob variations
(tp1 / sell-fraction / lock) of a much smaller set of structural setups
(trigger x strike x stop). This collapses them to DISTINCT setups, keeps the best
representative of each (by entry-alpha margin over the random-entry null, robustness-
weighted by quarter positivity), ranks them, and writes:
  - analysis/recommendations/vwap-elite-consolidation.json           (machine)
  - markdown/research/GRIND-VWAP-ELITE-CONSOLIDATION-<date>.md       (human shortlist)

Pure read of the vwap funnel JSONLs — no backtests, $0, no contention. Every P4 elite
already cleared verify_candidate (beat the null MAX AND drop-top5 beats null mean AND no
sign-inversion at chart-stop-only), so survivors are concentration-robust + entry-alpha
positive by construction. The open risks (multiple-testing across the 3,360-wide search +
the single 2025-2026 regime) are stated in the verdict so nothing flips live on in-sample
search alone — deploy path is forward paper-validation (fleet challenger).
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_ROOT = _REPO.parent
RECO = _ROOT / "analysis" / "recommendations"
OUT_JSON = RECO / "vwap-elite-consolidation.json"
# No dash before '*' so it matches the single-process file (mass-grind-vwap-funnel.jsonl)
# as well as any sharded files (mass-grind-vwap-funnel-0.jsonl).
FUNNEL_GLOB = "mass-grind-vwap-funnel*.jsonl"


def _stamp() -> str:
    return dt.date.today().isoformat()


def _load_elites() -> list[dict]:
    # Dedup by label (keep first): the funnel rows are deterministic, so a resumed/retried
    # funnel can legitimately have repeated labels — count each distinct cell once.
    out: list[dict] = []
    seen: set = set()
    for f in glob.glob(str(RECO / FUNNEL_GLOB)):
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("phase_reached") == 4 and r.get("label") not in seen:
                seen.add(r.get("label"))
                out.append(r)
    return out


def _setup_key(combo: list) -> str:
    # combo = [trig, bo, pv, sk, so, stop_label, sv, tp, tq, lk]
    trig, bo, pv, sk, so, stop_label, sv, tp, tq, lk = combo
    return f"{sk}|stop{stop_label}|{trig}"


def _edge_over_null(e: dict) -> float:
    p4 = e.get("p4") or {}
    v = p4.get("edge_over_null")
    return float(v) if v is not None else 0.0


def _score(e: dict) -> float:
    # entry-alpha margin over the null, robustness-weighted by quarter positivity
    return _edge_over_null(e) * float(e.get("qpf") or 0.0)


def main() -> int:
    elites = _load_elites()
    if not elites:
        print("no vwap P4 elites yet (funnel may still be running / none cleared P4)")
        # Still emit an empty machine file so the dashboard reads a defined state.
        OUT_JSON.write_text(json.dumps({
            "generated": dt.datetime.now().isoformat(timespec="seconds"),
            "family": "vwap_continuation", "total_p4_elites": 0, "distinct_setups": 0,
            "top_setups": [],
            "caveats": ["No vwap cell cleared P4 (beat-the-null + no-truncation) — a NONE "
                        "verdict is informative: the vwap entry's alpha did not survive the "
                        "fraud gates across the swept structures."],
        }, indent=2), encoding="utf-8")
        return 1

    families: dict[str, list[dict]] = defaultdict(list)
    for e in elites:
        families[_setup_key(e["combo"])].append(e)

    reps = []
    for key, group in families.items():
        best = max(group, key=_score)
        p4 = best.get("p4") or {}
        _cpt = p4.get("chosen_per_trade_default_exits")
        reps.append({
            "setup": key,
            "best_label": best["label"],
            "n_variations": len(group),
            "expectancy": round(float(best.get("expectancy") or 0.0), 1),
            "edge_capture": round(float(best.get("edge_capture") or 0.0), 0),
            "qpf": best.get("qpf"),
            "edge_over_null": p4.get("edge_over_null"),
            "null_max": p4.get("null_max"),
            "chosen_per_trade_default_exits": (round(float(_cpt), 2) if _cpt is not None else None),
            "wf": best.get("wf"),
            "n_trades": best.get("n"),
            "live_real_exp": best.get("live_real_exp"),
            "score": round(_score(best), 1),
        })
    reps.sort(key=lambda r: -(r["score"] or 0))

    summary = {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "family": "vwap_continuation",
        "total_p4_elites": len(elites),
        "distinct_setups": len(families),
        "top_setups": reps[:12],
        "caveats": [
            "3,360-config search => multiple-testing; the per-config null is NOT search-corrected.",
            "Single 2025-2026 regime; the null controls entry TIMING, not regime favorability.",
            "P4 isolates ENTRY alpha (default v15 exits); a combo's headline expectancy uses "
            "its specific swept exits — the two are reported separately.",
            "edge_capture (OP-16, J's bearish anchors) is disclosed but NOT a gate for this "
            "bull-tilted continuation family (C24/OP-16).",
            "Deploy path = forward paper-validation (fleet challenger), NOT a blind params.json flip.",
        ],
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    doc = _ROOT / "markdown" / "research" / f"GRIND-VWAP-ELITE-CONSOLIDATION-{_stamp()}.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# vwap_continuation grind elite consolidation — {_stamp()}",
        "",
        f"**{len(elites)} P4 elites collapse to {len(families)} distinct structural setups** "
        "(trigger x strike x stop). The rest are exit-knob fine-tuning of these.",
        "",
        "The SECOND family in the strategy table (the first grind covered only the ribbon "
        "rejection/reclaim entry). Every row below already beat the random-entry null MAX, kept "
        "its edge after dropping its 5 best days, AND did not invert sign at chart-stop-only "
        "(verify_candidate: null + no-truncation, the validated vwap fraud-gate harness).",
        "",
        "## Ranked distinct setups (best representative each)",
        "",
        "| # | setup | exp/tr | entry/tr (def exits) | +edge vs null | null max | qpf | WF | n | variations |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(reps[:12], 1):
        lines.append(
            f"| {i} | `{r['setup']}` | ${r['expectancy']:.0f} | "
            f"${r['chosen_per_trade_default_exits']} | +${r['edge_over_null']} | "
            f"${r['null_max']} | {r['qpf']} | {r['wf']} | {r['n_trades']} | {r['n_variations']} |"
        )
    if reps:
        top = reps[0]
        lines += [
            "",
            "## Verdict",
            "",
            f"**Top vwap_continuation setup:** `{top['setup']}` "
            f"(best variation `{top['best_label']}`, ${top['expectancy']:.0f}/trade headline, "
            f"+${top['edge_over_null']} entry-alpha over the coin-flip null).",
            "",
            "How this family differs from the ribbon table (the FIRST grind): the ribbon "
            "family is a bearish-rejection ride-the-ribbon directional trade gated on level "
            "rejection + min-triggers; this family is a **morning VWAP-side continuation** "
            "(first 3 RTH closes set the day side; first in-trend breakout/shallow-dip is the "
            "entry) — a structurally distinct, bull-tilted entry. It is also already LIVE "
            "(WP-8, ITM-2/-8%), so this grind maps the exit/strike/trigger neighborhood around "
            "a known edge rather than discovering one cold.",
            "",
            "**Why the elites are OTM-1, not ITM-2 (the live strike):** ITM-2 had the best RAW "
            "expectancy (~$100/tr) but the P3 live-realizability gate DEMOTED it — deep-ITM "
            "premium is too expensive to place at the live Safe-2 $2K / qty-5 tier (admit < 50%, "
            "L180). So the DEPLOYABLE elites are the cheaper OTM-1 strikes the live cap admits; "
            "ITM-2 re-enters only at a higher-equity tier where the per-trade $-cap stops binding.",
            "",
            "- **Not deploy-by-flip.** Searched 3,360 configs on ONE 2025-2026 regime; the "
            "per-config null is not search-corrected, and nothing here is confirmed on a "
            "held-out regime.",
            "- **Deploy path = forward paper-validation.** Freeze the top 1-3 distinct setups "
            "as fleet challengers and let them prove forward.",
        ]
    lines += [
        "",
        "_Generated by `autoresearch/consolidate_elites_vwap.py` (pure read; $0)._",
    ]
    doc.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[consolidate-vwap] {len(elites)} elites -> {len(families)} distinct setups")
    if reps:
        top = reps[0]
        print(f"[consolidate-vwap] top: {top['setup']}  ${top['expectancy']:.0f}/tr  "
              f"+${top['edge_over_null']} vs null")
    print(f"[consolidate-vwap] wrote {OUT_JSON.name} + {doc.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
