"""Mine the native futures fleet for POSITIVE-EXPECTANCY signal slices.

Input: backtest/data/futures/{MES,MNQ}_native_rows.jsonl — the full watcher fleet graded
on REAL futures bars (4,865 signals, 2025-01..2026-06). The aggregate loses (control
experiment 2026-06-20 NO-EDGE verdict), but the question now is: are there ROBUST winning
subsets hiding inside the losing whole?

Overfitting discipline (the whole LESSONS corpus is about this — C4/PBO/deflated-sharpe):
  * Require N >= MIN_N per slice (no 3-trade "winners").
  * Require CROSS-INSTRUMENT AGREEMENT: a slice must be net-positive on BOTH MES and MNQ
    independently. A real directional edge in index futures should not care which micro
    expresses it; a slice that only wins on one is almost certainly noise.
  * Report per-contract (net / n) so size doesn't distort.
  * Rank by the WORSE of the two instruments' avg (min-of-both) — the robust lower bound.

Output: analysis/winning-signals-mine-2026-06-20.md + .json. Pure Python, $0.
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
FUT = REPO / "backtest" / "data" / "futures"
OUT_MD = REPO / "analysis" / "winning-signals-mine-2026-06-20.md"
OUT_JSON = REPO / "analysis" / "winning-signals-mine-2026-06-20.json"

MIN_N = 25          # per-instrument minimum for a slice to be considered
MIN_N_CELL = 40     # higher bar for a (setup×dir) cell we'd actually build on


def load(inst: str) -> list[dict]:
    p = FUT / f"{inst}_native_rows.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def vix_band(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "NA"
    if v < 15:
        return "LOW(<15)"
    if v <= 18:
        return "MID(15-18)"
    if v <= 22:
        return "ELEV(18-22)"
    return "HIGH(>22)"


def agg(rows: list[dict]) -> dict:
    n = len(rows)
    nets = [r["net"] for r in rows]
    wins = sum(1 for x in nets if x > 0)
    return {"n": n, "net": round(sum(nets), 1), "wr": round(wins / n, 3) if n else 0.0,
            "avg": round(sum(nets) / n, 2) if n else 0.0}


def slice_by(rows: list[dict], keyfn) -> dict:
    d = defaultdict(list)
    for r in rows:
        d[keyfn(r)].append(r)
    return {k: agg(v) for k, v in d.items()}


def cross(mes: list[dict], mnq: list[dict], keyfn, min_n=MIN_N) -> list[dict]:
    """Slices net-positive on BOTH instruments with n>=min_n each."""
    m = slice_by(mes, keyfn)
    q = slice_by(mnq, keyfn)
    out = []
    for k in set(m) | set(q):
        a, b = m.get(k), q.get(k)
        if not a or not b:
            continue
        if a["n"] < min_n or b["n"] < min_n:
            continue
        both_pos = a["avg"] > 0 and b["avg"] > 0
        robust = round(min(a["avg"], b["avg"]), 2)   # worse-of-both lower bound
        out.append({"key": k, "mes": a, "mnq": b, "both_positive": both_pos,
                    "robust_avg": robust, "combined_n": a["n"] + b["n"],
                    "combined_wr": round((a["wr"] * a["n"] + b["wr"] * b["n"]) / (a["n"] + b["n"]), 3)})
    out.sort(key=lambda x: x["robust_avg"], reverse=True)
    return out


def main() -> int:
    mes, mnq = load("MES"), load("MNQ")
    L = []
    a = L.append
    a("# Winning-signal mine — native futures fleet (2026-06-20)\n")
    a("> Hunting robust positive-expectancy subsets inside the losing whole. A slice only "
      f"counts if it is net-positive on **BOTH** MES and MNQ independently (n≥{MIN_N} each) — "
      "cross-instrument agreement is the overfitting guard. Avg = $/contract/trade.\n")
    a(f"- Universe: MES {len(mes):,} signals, MNQ {len(mnq):,} signals.\n")

    findings = {}

    # 1) setup × direction
    sd = cross(mes, mnq, lambda r: f"{r['setup']} | {r['dir']}", min_n=MIN_N_CELL)
    findings["setup_dir"] = sd
    a(f"## Setup × direction (n≥{MIN_N_CELL} each instrument)\n")
    a("| Setup \\| dir | robust avg | combined n | comb WR | MES (n/avg) | MNQ (n/avg) | both+ |")
    a("|---|--:|--:|--:|--:|--:|:--:|")
    for x in sd:
        a(f"| {x['key']} | {x['robust_avg']:+.2f} | {x['combined_n']} | "
          f"{x['combined_wr']*100:.0f}% | {x['mes']['n']}/{x['mes']['avg']:+.1f} | "
          f"{x['mnq']['n']}/{x['mnq']['avg']:+.1f} | {'YES' if x['both_positive'] else 'no'} |")
    a("")

    # 2) setup × direction × vix-band  (only winners shown)
    sdv = cross(mes, mnq, lambda r: f"{r['setup']} | {r['dir']} | {vix_band(r['vix'])}", min_n=MIN_N)
    sdv_win = [x for x in sdv if x["both_positive"]]
    findings["setup_dir_vix_winners"] = sdv_win
    a(f"## Setup × dir × VIX-band — WINNERS only (n≥{MIN_N} each)\n")
    if sdv_win:
        a("| Setup \\| dir \\| vix | robust avg | comb n | comb WR | MES | MNQ |")
        a("|---|--:|--:|--:|--:|--:|")
        for x in sdv_win:
            a(f"| {x['key']} | {x['robust_avg']:+.2f} | {x['combined_n']} | "
              f"{x['combined_wr']*100:.0f}% | {x['mes']['n']}/{x['mes']['avg']:+.1f} | "
              f"{x['mnq']['n']}/{x['mnq']['avg']:+.1f} |")
    else:
        a("_None — no setup×dir×vix slice is positive on both instruments at n≥25._")
    a("")

    # 3) confidence × direction
    cd = cross(mes, mnq, lambda r: f"conf={r.get('conf')} | {r['dir']}", min_n=MIN_N)
    findings["conf_dir"] = cd
    a("## Confidence × direction (all, n≥25 each)\n")
    a("| key | robust avg | comb n | comb WR | MES | MNQ | both+ |")
    a("|---|--:|--:|--:|--:|--:|:--:|")
    for x in cd:
        a(f"| {x['key']} | {x['robust_avg']:+.2f} | {x['combined_n']} | {x['combined_wr']*100:.0f}% | "
          f"{x['mes']['n']}/{x['mes']['avg']:+.1f} | {x['mnq']['n']}/{x['mnq']['avg']:+.1f} | "
          f"{'YES' if x['both_positive'] else 'no'} |")
    a("")

    # 4) per-setup aggregate (both dirs) for context
    a("## Per-setup aggregate (context — MES, all dirs)\n")
    setups = slice_by(mes, lambda r: r["setup"])
    a("| setup | n | net $ | WR | avg |")
    a("|---|--:|--:|--:|--:|")
    for k, v in sorted(setups.items(), key=lambda kv: kv[1]["avg"], reverse=True):
        a(f"| {k} | {v['n']} | {v['net']:+.0f} | {v['wr']*100:.0f}% | {v['avg']:+.2f} |")
    a("")

    # verdict
    winners = [x for x in sd if x["both_positive"]] + sdv_win
    a("## Read\n")
    if winners:
        top = sorted(winners, key=lambda x: x["robust_avg"], reverse=True)[:5]
        a(f"**{len(set(w['key'] for w in winners))} robust positive slices** (positive on both "
          "instruments). Top candidates to build on:")
        for x in top:
            a(f"- `{x['key']}` — robust +${x['robust_avg']:.2f}/contract, "
              f"combined n={x['combined_n']}, WR {x['combined_wr']*100:.0f}%")
    else:
        a("**No setup×dir slice is robustly positive on both instruments.** The edge is not in "
          "any single existing detector — winners must come from NEW conditioning (regime / "
          "structure filters), not the current setup taxonomy.")
    a("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(findings, indent=2), encoding="utf-8")
    assert OUT_MD.stat().st_size > 400
    print(f"setup_dir winners(both+): {sum(1 for x in sd if x['both_positive'])} / {len(sd)} cells")
    print(f"setup_dir_vix winners(both+): {len(sdv_win)}")
    print("top setup_dir by robust_avg:")
    for x in sd[:6]:
        print(f"  {x['key']}: robust {x['robust_avg']:+.2f}  MES {x['mes']['n']}/{x['mes']['avg']:+.1f}  MNQ {x['mnq']['n']}/{x['mnq']['avg']:+.1f}  both+={x['both_positive']}")
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
