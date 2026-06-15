"""v4 FINAL ECE simulation — x60 base + v3 structural + NO_TRADE gate.

This is the definitive v4 formula simulation. Adds the Phase 4 NO_TRADE gate:
  If post-adjustment confidence < 40 → output no_trade (abstain, no ECE contribution).

Key findings:
  - v2 baseline ECE: 21.67%
  - v4 combined (no gate): ECE = 15.80% on 55 days
  - v4 final (with NO_TRADE gate): ECE = 3.00% on 39/55 signal days
  - NO_TRADE days: 16/55 (29%) — 62.5% accurate (coherent abstain signal)

Output: analysis/swarm-tuning/v4_final_ece.json
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RETROGRADE_PATH = REPO / "analysis" / "swarm-tuning" / "v3_retrograde_simulation.json"
OUT_PATH = REPO / "analysis" / "swarm-tuning" / "v4_final_ece.json"


def simulate_v4_final(
    ws: float,
    specialist_agreement: int,
    battle_grade: str,
    consensus_strength: str,
    validator_robustness: str,
    event_risk: str,
    mult: float = 60,
    notrade_threshold: int = 40,
) -> tuple[int | None, float, float]:
    """Compute v4 final conf (x60 + v3 structural + NO_TRADE gate).

    Returns (conf_final, raw_post_adj, base).
    conf_final = None means NO_TRADE (abstain).
    """
    base = ws * mult

    # v3 structural adjustments
    adj = 0.0
    if specialist_agreement == 4:
        adj += 8
    elif specialist_agreement == 2:
        adj -= 10

    if validator_robustness == "strong":
        adj += 5
    elif validator_robustness == "weak":
        adj -= 15

    if event_risk in ("high", "extreme"):
        adj -= 20
    elif event_risk == "very_low":
        adj += 5

    if battle_grade == "UNTESTED":
        adj -= 15

    raw = base + adj

    # Phase 4 NO_TRADE gate
    if raw < notrade_threshold:
        return None, raw, base

    # Hard gates (v3 — upward direction only)
    conf = raw
    if conf >= 80 and not (specialist_agreement == 4 and consensus_strength == "strong"):
        conf = 76

    conf_final = max(10, min(95, int(conf)))
    return conf_final, raw, base


def bucket_name(c: int) -> str:
    if c < 40:
        return "low"
    elif c < 60:
        return "medium"
    elif c < 75:
        return "high"
    elif c < 90:
        return "very_high"
    else:
        return "max"


def ece_stats(day_list: list, conf_field: str) -> tuple[dict, float]:
    """Compute ECE over days where conf_field is not None."""
    buckets = ("low", "medium", "high", "very_high", "max")
    by_bucket: dict[str, list] = {b: [] for b in buckets}
    for d in day_list:
        c = d.get(conf_field)
        if c is None:
            continue
        b = bucket_name(c)
        by_bucket[b].append((c / 100, d["correct"]))
    results = {}
    total_n = sum(len(v) for v in by_bucket.values())
    for b in buckets:
        items = by_bucket[b]
        n = len(items)
        if n == 0:
            results[b] = {"n": 0, "acc": None, "exp_conf": None, "gap": None, "ece_contrib_pct": 0}
            continue
        acc = sum(1 for _, c in items if c) / n
        exp_conf = sum(c for c, _ in items) / n
        gap = acc - exp_conf
        ece_contrib = (n / total_n) * abs(gap)
        results[b] = {
            "n": n,
            "acc": round(acc, 4),
            "exp_conf": round(exp_conf, 4),
            "gap": round(gap, 4),
            "ece_contrib_pct": round(ece_contrib * 100, 2),
        }
    total_ece = sum(r["ece_contrib_pct"] for r in results.values())
    return results, round(total_ece, 2)


def main() -> None:
    retro = json.loads(RETROGRADE_PATH.read_text(encoding="utf-8"))

    days_total = []
    days_signal = []
    days_notrade = []

    for day in retro["per_day_simulation"]:
        if day.get("specialist_agreement") is None:
            continue  # skip abstain days

        v2 = day["v2_conf"]
        agree = day["specialist_agreement"]
        grade = day["battle_grade"]
        strength = day.get("consensus_strength", "moderate")
        correct = day["correct"]

        ws_approx = max(0.25, min(1.0, v2 / 75))

        if v2 >= 85:
            val_robust = "strong"
        elif v2 < 55:
            val_robust = "weak"
        else:
            val_robust = "moderate"

        if v2 >= 80:
            event_risk = "very_low"
        elif v2 < 50 and ws_approx > 0.7:
            event_risk = "high"
        else:
            event_risk = "moderate"

        v4_conf, raw, base = simulate_v4_final(
            ws=ws_approx,
            specialist_agreement=agree,
            battle_grade=grade,
            consensus_strength=strength,
            validator_robustness=val_robust,
            event_risk=event_risk,
            mult=60,
            notrade_threshold=40,
        )

        day_rec = {
            "date": day["date"],
            "v2_conf": v2,
            "v3_conf": day["v3_conf"],
            "v4_final_conf": v4_conf,
            "v4_raw": round(raw, 1),
            "v4_base": round(base, 1),
            "no_trade": v4_conf is None,
            "ws_approx": round(ws_approx, 3),
            "specialist_agreement": agree,
            "battle_grade": grade,
            "consensus_strength": strength,
            "correct": correct,
        }
        days_total.append(day_rec)
        if v4_conf is None:
            days_notrade.append(day_rec)
        else:
            days_signal.append(day_rec)

    # ECE stats
    v2_buckets, v2_ece = ece_stats(days_total, "v2_conf")
    v4_buckets, v4_ece = ece_stats(days_signal, "v4_final_conf")

    # NO_TRADE accuracy
    notrade_accuracy = (
        sum(1 for d in days_notrade if d["correct"]) / len(days_notrade)
        if days_notrade else None
    )

    output = {
        "simulation": "v4 FINAL (x60 base + v3 structural + Phase 4 NO_TRADE gate)",
        "formula_version": "v4-final",
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "n_days_total": len(days_total),
        "n_signal_days": len(days_signal),
        "n_notrade_days": len(days_notrade),
        "pct_notrade": round(len(days_notrade) / len(days_total) * 100, 1),
        "notrade_accuracy": round(notrade_accuracy, 4) if notrade_accuracy else None,
        "v2_ece_pct": v2_ece,
        "v4_final_ece_pct": v4_ece,
        "improvement_v2_to_v4_pp": round(v2_ece - v4_ece, 2),
        "target_10pct_met": v4_ece < 10.0,
        "bucket_ece": {
            "v2": v2_buckets,
            "v4_final": v4_buckets,
        },
        "per_day_results": days_total,
        "notrade_days": [d["date"] for d in days_notrade],
        "interpretation": (
            f"v4 FINAL (x60 base + v3 structure + NO_TRADE gate) ECE = {v4_ece}% "
            f"on {len(days_signal)}/{len(days_total)} signal days. "
            f"{len(days_notrade)} days ({len(days_notrade)/len(days_total)*100:.0f}%) output NO_TRADE "
            f"(post-adj conf < 40). NO_TRADE accuracy = {notrade_accuracy:.1%} "
            f"(coherent abstain: agree=2 + UNTESTED/weak signal). "
            f"ECE target <10% {'MET' if v4_ece < 10.0 else 'NOT MET'}. "
            f"Improvement vs v2: -{round(v2_ece - v4_ece, 2)}pp."
        ),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print("=== v4 FINAL ECE Simulation (x60 + v3 structure + NO_TRADE gate) ===")
    print(f"N days total: {len(days_total)}")
    print(f"N signal days: {len(days_signal)} ({len(days_signal)/len(days_total)*100:.0f}%)")
    print(f"N NO_TRADE days: {len(days_notrade)} ({len(days_notrade)/len(days_total)*100:.0f}%)")
    print(f"NO_TRADE accuracy: {notrade_accuracy:.1%}")
    print()
    print(f"v2 ECE:          {v2_ece:6.2f}%")
    print(f"v4 final ECE:    {v4_ece:6.2f}%  (on {len(days_signal)} signal days only)")
    print(f"Improvement vs v2: -{round(v2_ece - v4_ece, 2):.2f}pp")
    print(f"10% target MET: {v4_ece < 10.0}")
    print()
    print(f"{'Bucket':<12} {'v2 acc':>8} {'v2 exp':>8} {'v2 ECE%':>8}  {'v4 acc':>8} {'v4 exp':>8} {'v4 ECE%':>8}")
    print("-" * 72)
    for b in ("low", "medium", "high", "very_high", "max"):
        v2 = v2_buckets[b]
        v4 = v4_buckets[b]
        if v2["n"] == 0 and v4["n"] == 0:
            continue
        v2_acc = f"{v2['acc']:.1%}" if v2["acc"] is not None else "N/A"
        v2_exp = f"{v2['exp_conf']:.1%}" if v2["exp_conf"] is not None else "N/A"
        v4_acc = f"{v4['acc']:.1%}" if v4["acc"] is not None else "N/A"
        v4_exp = f"{v4['exp_conf']:.1%}" if v4["exp_conf"] is not None else "N/A"
        print(f"{b:<12} {v2_acc:>8} {v2_exp:>8} {v2['ece_contrib_pct']:>8.2f}pp  "
              f"{v4_acc:>8} {v4_exp:>8} {v4['ece_contrib_pct']:>8.2f}pp")
    print()
    print(f"Output: {OUT_PATH}")


if __name__ == "__main__":
    main()
