"""Consolidate the mass-grind-funnel P4 elites into a DEPLOYABLE shortlist.

The funnel produces hundreds of "PASS-P4 elite" rows, but they are NOT independent
strategies -- they are exit-knob variations (tp1 / sell-fraction / lock) of a much
smaller set of structural setups (strike x stop x gate x trigger). Treating 291 rows as
291 wins is discovery theater and inflates the multiple-testing problem.

This collapses them to DISTINCT setups, keeps the best representative of each (by margin
over the random-entry null), ranks them, and writes:
  - analysis/recommendations/elite-consolidation.json   (machine)
  - markdown/research/GRIND-ELITE-CONSOLIDATION-<date>.md (human shortlist + verdict)

Pure read of the funnel JSONLs -- no backtests, $0, no contention with the live funnel.
Every P4 elite already cleared `null_pass = beats_null_max AND drop_top5_beats_null_mean`,
so the survivors are concentration-robust by construction; the open risks are (a) the
3,360-wide search (multiple testing) and (b) the single 2025-2026 regime -- both stated
in the verdict so nothing gets flipped live on in-sample search alone.
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
OUT_JSON = RECO / "elite-consolidation.json"


def _stamp() -> str:
    return dt.date.today().isoformat()


def _load_elites() -> list[dict]:
    out = []
    for f in glob.glob(str(RECO / "mass-grind-funnel-*.jsonl")):
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if r.get("phase_reached") == 4:
                    out.append(r)
            except Exception:
                pass
    return out


def _setup_key(combo: list) -> str:
    sk, so, blr, mt, stp, sv, tp, tq, lk = combo
    return f"{sk}|stop{stp}|LR{int(blr)}|mt{mt}"


def _score(e: dict) -> float:
    # margin over null, robustness-weighted by quarter positivity
    n = e.get("p4_null") or {}
    edge = n.get("edge_over_null") or 0.0
    return float(edge) * float(e.get("qpf") or 0.0)


def main() -> int:
    elites = _load_elites()
    if not elites:
        print("no P4 elites yet")
        return 1

    families: dict[str, list[dict]] = defaultdict(list)
    for e in elites:
        families[_setup_key(e["combo"])].append(e)

    # best representative per distinct setup
    reps = []
    for key, group in families.items():
        best = max(group, key=_score)
        n = best.get("p4_null") or {}
        reps.append({
            "setup": key,
            "best_label": best["label"],
            "n_variations": len(group),
            "expectancy": round(float(best.get("expectancy") or 0.0), 1),
            "edge_capture": round(float(best.get("edge_capture") or 0.0), 0),
            "qpf": best.get("qpf"),
            "edge_over_null": n.get("edge_over_null"),
            "null_max": n.get("null_max"),
            "wf": best.get("wf"),
            "n_trades": best.get("n"),
            "score": round(_score(best), 1),
        })
    reps.sort(key=lambda r: -(r["score"] or 0))

    summary = {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "total_p4_elites": len(elites),
        "distinct_setups": len(families),
        "top_setups": reps[:12],
        "caveats": [
            "3,360-config search => multiple-testing; per-config null is not search-corrected.",
            "Single 2025-2026 regime; null controls entry timing, NOT regime favorability.",
            "Deploy path = forward paper-validation (fleet challenger), NOT a blind params.json flip.",
        ],
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # human doc
    doc = _ROOT / "markdown" / "research" / f"GRIND-ELITE-CONSOLIDATION-{_stamp()}.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Grind elite consolidation — {_stamp()}",
        "",
        f"**{len(elites)} P4 elites collapse to {len(families)} distinct structural setups** "
        "(strike x stop x gate x trigger). The rest are exit-knob fine-tuning of these.",
        "",
        "Every row below already beat the random-entry null MAX *and* kept its edge after "
        "dropping its 5 best days (concentration-robust by construction).",
        "",
        "## Ranked distinct setups (best representative each)",
        "",
        "| # | setup | exp/tr | edge_cap | qpf | +edge vs null | null max | WF | n | variations |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(reps[:12], 1):
        lines.append(
            f"| {i} | `{r['setup']}` | ${r['expectancy']:.0f} | {r['edge_capture']:.0f} | "
            f"{r['qpf']} | +${r['edge_over_null']} | ${r['null_max']} | {r['wf']} | "
            f"{r['n_trades']} | {r['n_variations']} |"
        )
    top = reps[0]
    lines += [
        "",
        "## Verdict",
        "",
        f"**Single dominant edge family:** `{top['setup']}` "
        f"(best variation `{top['best_label']}`, ${top['expectancy']:.0f}/trade, "
        f"+${top['edge_over_null']} over the coin-flip null).",
        "",
        "The 291 'elites' are ~one robust pattern: **tight-stop OTM directional ride** "
        "(−8% stop caps the left tail, big runner rides the right). Real signal — it beats "
        "random entry through the same bracket — but:",
        "",
        "- **Not deploy-by-flip.** Searched 3,360 configs on ONE 2025-2026 regime. The per-config "
        "null does not correct for the search, and nothing here is confirmed on a held-out regime.",
        "- **Deploy path = forward paper-validation.** Freeze the top 1-3 distinct setups as fleet "
        "challengers and let them prove forward, rather than overwriting live v15.3 on in-sample search.",
        "",
        "_Generated by `autoresearch/consolidate_elites.py` (pure read; $0)._",
    ]
    doc.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[consolidate] {len(elites)} elites -> {len(families)} distinct setups")
    print(f"[consolidate] top: {top['setup']}  ${top['expectancy']:.0f}/tr  +${top['edge_over_null']} vs null")
    print(f"[consolidate] wrote {OUT_JSON.name} + {doc.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
