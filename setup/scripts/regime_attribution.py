"""regime_attribution.py -- nightly REGIME-CONDITIONAL P&L ATTRIBUTION (LENS 4, 2026-08-04).

THE QUESTION THIS EXISTS TO ANSWER WITHOUT A LENS: after a big day, "was that us or was that
the tape?" On 2026-08-04 the fleet made +$3,624 -- 145% of its entire prior live record -- and
answering that question took a full research session. It should take a JSON read. This is the
standing instrument (OP-33(e): a repeated question is a missing instrument, not a query).

WHAT IT COMPUTES (frozen definitions v1-2026-08-04 -- a change is a version bump)
---------------------------------------------------------------------------------
  archetype            the day's mechanical shape from analysis/regime-library/day-archetypes.json
                       (DESCRIPTIVE, post-hoc, whole-session -- never feeds a live entry).
  archetype_share      P(this archetype) over the assignable population. "How often does a day
                       that looks like this even happen."
  archetype_mean_prior mean real-fill day P&L on PRIOR days of the same archetype. Excludes the
                       graded day itself -- a day must never help set the bar it is graded
                       against. None until a prior day of that archetype exists (loud, not 0).
  regime_lift          today_pnl - archetype_mean_prior. The part a "days like this pay X"
                       story does NOT explain.
  mix_ev               sum over archetypes of P(archetype) * mean_pnl(archetype), using the
                       FULL live record. The honest expected day given the population mix and
                       our own fills -- the number that says whether a headline day is a
                       weekly baseline or a 1-in-N event.
  concentration        top-1 and top-2 round trips as a share of the day's GROSS POSITIVE P&L,
                       plus n_roundtrips. The "was this actually two trades?" number: on
                       2026-08-04 two entry clusters produced +$4,363 gross while the other 23
                       round trips lost -$739.
  sizing_era           equity band of the arms (from the round trips' own accounts) -- cross-era
                       dollar comparisons are apples-to-oranges and this field says so rather
                       than letting a reader forget.

HONEST BY CONSTRUCTION: every figure comes from broker-verified FIFO round trips
(automation/state/fills-ledger.jsonl via automation/state/fleet/fills_fifo.py, attribution=
'engine' only) joined to a deterministic archetype library. No model, no simulation, no LLM,
no network. STDLIB ONLY so it runs from any interpreter on a $0 scheduled fire.

FAIL-OPEN, ALWAYS (OP-25): an untagged date, a missing library, or an empty ledger produces a
report with status set and reason stated -- never an exception, never a blocked session.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

from fills_fifo import mine_real_arm_fills  # noqa: E402

DEFN_VERSION = "v1-2026-08-04"
ARMS = ("safe-2", "bold-2", "safe-3", "risky-1", "risky-3")
LIBRARY = REPO / "analysis" / "regime-library" / "day-archetypes.json"
OUT_JSON = REPO / "automation" / "state" / "regime-attribution.json"
HISTORY = REPO / "analysis" / "regime-library" / "attribution-history.jsonl"
DATA_INCOMPLETE = "data-incomplete"


# ---------------------------------------------------------------------------
# pure functions (unit-tested -- backtest/tests/test_regime_attribution_2026_08_04.py)
# ---------------------------------------------------------------------------
def archetype_share(library_days: dict, archetype: str) -> Optional[float]:
    """P(archetype) over the ASSIGNABLE population (data-incomplete sessions excluded, per the
    regime library's own distribution rule)."""
    assignable = [r for r in library_days.values() if r.get("archetype") != DATA_INCOMPLETE]
    if not assignable:
        return None
    return round(sum(1 for r in assignable if r.get("archetype") == archetype) / len(assignable), 4)


def prior_mean(day_pnl: dict, library_days: dict, archetype: str, as_of: str) -> tuple[Optional[float], int]:
    """(mean, n) of real day P&L on days of `archetype` STRICTLY BEFORE `as_of`.

    Strictly-before is the whole point: grading a day against a mean it helped compute is the
    look-ahead that makes every headline day look average. Returns (None, 0) when no prior day
    of that archetype has traded -- the caller reports 'no prior', never a fabricated 0.0."""
    vals = [v for d, v in day_pnl.items()
            if d < as_of and (library_days.get(d) or {}).get("archetype") == archetype]
    if not vals:
        return None, 0
    return round(sum(vals) / len(vals), 2), len(vals)


def mix_ev(day_pnl: dict, library_days: dict) -> Optional[float]:
    """sum_a P(a) * mean_pnl(a). Archetypes we have never traded contribute 0 weight (their
    probability mass is renormalised away) -- disclosed via `mix_ev_coverage`."""
    means: dict[str, float] = {}
    counts: dict[str, int] = {}
    for d, v in day_pnl.items():
        a = (library_days.get(d) or {}).get("archetype")
        if not a or a == DATA_INCOMPLETE:
            continue
        means[a] = means.get(a, 0.0) + v
        counts[a] = counts.get(a, 0) + 1
    if not counts:
        return None
    weights = {a: archetype_share(library_days, a) or 0.0 for a in counts}
    total_w = sum(weights.values())
    if total_w <= 0:
        return None
    return round(sum((weights[a] / total_w) * (means[a] / counts[a]) for a in counts), 2)


def mix_ev_coverage(day_pnl: dict, library_days: dict) -> float:
    """Share of the population's probability mass covered by archetypes we have actually
    traded. A low number means mix_ev is extrapolating from a narrow slice of market shapes."""
    seen = {(library_days.get(d) or {}).get("archetype") for d in day_pnl}
    seen.discard(None)
    seen.discard(DATA_INCOMPLETE)
    return round(sum(archetype_share(library_days, a) or 0.0 for a in seen), 4)


def concentration(roundtrips: list[dict]) -> dict:
    """How much of the day's GROSS POSITIVE P&L came from its 1 and 2 best round trips.

    Denominator is gross POSITIVE (not net): on a day whose net is small but whose gross swings
    are large, a net denominator produces a meaningless >100% share -- and on a losing day it
    would flip sign. Gross-positive keeps the ratio in [0, 1] and interpretable on every day."""
    pnls = sorted((float(r["real_pnl"]) for r in roundtrips), reverse=True)
    gross_pos = sum(p for p in pnls if p > 0)
    if gross_pos <= 0:
        return {"n_roundtrips": len(pnls), "gross_positive": round(gross_pos, 2),
                "top1_share": None, "top2_share": None,
                "gross_negative": round(sum(p for p in pnls if p < 0), 2)}
    return {"n_roundtrips": len(pnls), "gross_positive": round(gross_pos, 2),
            "gross_negative": round(sum(p for p in pnls if p < 0), 2),
            "top1_share": round(pnls[0] / gross_pos, 4) if pnls else None,
            "top2_share": round(sum(pnls[:2]) / gross_pos, 4) if len(pnls) >= 2 else None}


def verdict(today_pnl: float, mean_prior: Optional[float], share: Optional[float],
            conc: dict) -> str:
    """One line a human can act on. Deliberately blunt -- no hedging filler."""
    if not conc["n_roundtrips"]:
        return "NO TRADES -- nothing to attribute."
    bits = []
    if share is not None:
        bits.append(f"a day of this shape is {share * 100:.1f}% of the population "
                    f"(1 in {round(1 / share) if share else '-'})")
    if mean_prior is None:
        bits.append("NO PRIOR day of this archetype has traded -- today IS the sample, n=1")
    else:
        lift = today_pnl - mean_prior
        bits.append(f"prior days of this shape averaged ${mean_prior:,.2f}; "
                    f"today is ${lift:+,.2f} vs that")
    t2 = conc.get("top2_share")
    if t2 is not None and t2 >= 0.60:
        bits.append(f"{t2 * 100:.0f}% of gross-positive P&L came from 2 round trips of "
                    f"{conc['n_roundtrips']} -- CONCENTRATED, not broad")
    return "; ".join(bits) + "."


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------
def load_library() -> dict:
    if not LIBRARY.exists():
        return {}
    try:
        return json.loads(LIBRARY.read_text(encoding="ascii")).get("days", {})
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def day_pnl_map() -> tuple[dict, dict]:
    """(date -> total real P&L across arms, date -> list of round trips)."""
    totals: dict[str, float] = {}
    rts: dict[str, list] = {}
    for arm in ARMS:
        for r in mine_real_arm_fills(arm):
            d = r["date"]
            totals[d] = totals.get(d, 0.0) + float(r["real_pnl"])
            rts.setdefault(d, []).append(dict(r, arm=arm))
    return {k: round(v, 2) for k, v in totals.items()}, rts


def latest_traded_date(totals: dict) -> Optional[str]:
    return max(totals) if totals else None


def build_report(date_et: Optional[str] = None) -> dict:
    lib = load_library()
    totals, rts = day_pnl_map()
    target = date_et or latest_traded_date(totals)
    base = {"defn_version": DEFN_VERSION, "generated_date_et": dt.date.today().isoformat(),
            "date_et": target}
    if not lib:
        return dict(base, status="NO_LIBRARY",
                    reason=f"missing/unreadable {LIBRARY} -- run backtest/tools/build_day_archetypes.py")
    if target is None:
        return dict(base, status="NO_FILLS", reason="fills-ledger has no engine round trips")
    rec = lib.get(target)
    if rec is None:
        return dict(base, status="UNTAGGED",
                    reason=(f"{target} is not in the archetype library -- rebuild it "
                            "(backtest/tools/build_day_archetypes.py) once the day's 5m bars land"),
                    day_pnl=totals.get(target))
    arch = rec["archetype"]
    day = rts.get(target, [])
    pnl = totals.get(target, 0.0)
    share = archetype_share(lib, arch)
    mean_p, n_prior = prior_mean(totals, lib, arch, target)
    conc = concentration(day)
    per_arm: dict[str, float] = {}
    for r in day:
        per_arm[r["arm"]] = round(per_arm.get(r["arm"], 0.0) + float(r["real_pnl"]), 2)
    return dict(base,
                status="OK", archetype=arch, archetype_share=share,
                day_pnl=round(pnl, 2), per_arm=per_arm,
                archetype_mean_prior=mean_p, archetype_n_prior=n_prior,
                regime_lift=(None if mean_p is None else round(pnl - mean_p, 2)),
                mix_ev=mix_ev(totals, lib), mix_ev_coverage=mix_ev_coverage(totals, lib),
                concentration=conc,
                live_record={"n_days": len(totals), "total": round(sum(totals.values()), 2),
                             "total_ex_today": round(sum(v for d, v in totals.items()
                                                         if d != target), 2)},
                day_features={k: rec.get(k) for k in
                              ("range_pct", "body_pct", "close_loc", "open_loc",
                               "gap_pct", "vix_close", "t_high", "t_low")},
                verdict=verdict(pnl, mean_p, share, conc))


def upsert_history(report: dict) -> None:
    """Idempotent by date -- a re-run rewrites the row rather than appending a duplicate
    (the pattern violin_metric.py established; OP-22 retention discipline)."""
    if report.get("status") != "OK":
        return
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if HISTORY.exists():
        for line in HISTORY.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("date_et") != report["date_et"]:
                rows.append(row)
    keep = ("date_et", "archetype", "archetype_share", "day_pnl", "archetype_mean_prior",
            "archetype_n_prior", "regime_lift", "mix_ev", "concentration", "per_arm")
    rows.append({k: report.get(k) for k in keep})
    rows.sort(key=lambda r: r.get("date_et") or "")
    HISTORY.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows),
                       encoding="utf-8")


def render(report: dict) -> str:
    if report.get("status") != "OK":
        return f"REGIME-ATTRIBUTION [{report.get('status')}] {report.get('reason', '')}"
    c = report["concentration"]
    lines = [
        f"REGIME-ATTRIBUTION {report['date_et']}  archetype={report['archetype']} "
        f"({(report['archetype_share'] or 0) * 100:.1f}% of population)",
        f"  day P&L ${report['day_pnl']:,.2f}   " +
        "  ".join(f"{a}=${v:,.0f}" for a, v in sorted(report["per_arm"].items())),
        f"  prior days of this archetype: n={report['archetype_n_prior']} "
        f"mean=" + (f"${report['archetype_mean_prior']:,.2f}"
                    if report["archetype_mean_prior"] is not None else "n/a")
        + f"   regime_lift=" + (f"${report['regime_lift']:,.2f}"
                                if report["regime_lift"] is not None else "n/a"),
        f"  concentration: {c['n_roundtrips']} round trips, gross+ ${c['gross_positive']:,.2f} "
        f"gross- ${c['gross_negative']:,.2f}, top2 share="
        + (f"{c['top2_share'] * 100:.0f}%" if c["top2_share"] is not None else "n/a"),
        f"  mix_ev=${report['mix_ev']:,.2f}/day (archetype coverage "
        f"{report['mix_ev_coverage'] * 100:.0f}% of population mass)",
        f"  live record: {report['live_record']['n_days']} days "
        f"${report['live_record']['total']:,.2f} total "
        f"(${report['live_record']['total_ex_today']:,.2f} excluding this day)",
        f"  VERDICT: {report['verdict']}",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--nightly", action="store_true", help="grade the latest traded session")
    ap.add_argument("--date", default=None, help="grade a specific ISO date instead")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    try:
        report = build_report(args.date)
    except Exception as exc:  # fail-open by contract: never raise into a scheduled fire
        report = {"defn_version": DEFN_VERSION, "status": "ERROR", "reason": repr(exc),
                  "generated_date_et": dt.date.today().isoformat()}
    print(render(report))
    if not args.no_write:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")
        upsert_history(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
