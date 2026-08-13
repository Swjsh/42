"""conviction.py — the POSITIVE-EVIDENCE score the engine never had.

WHY THIS EXISTS (2026-08-12). The engine's scores count ABSENT OBJECTIONS, not present
reasons: `bear_score = 10 - len(blockers)` (filters.py:1758), `bull_score = 11 - len(blockers)`
(:1273). Every filter is a permission check. There is no term anywhere for *edge being
present* — level quality, multi-day memory, freshness of test, range location, confluence
density. On a day when nothing objects, everything is a trade. J, after a 38-position −$900
day: "it has no way to sit out… it needs to think more like a human instead of finding
thirty-eight reasons to trade."

Proof the existing axis is not a quality axis: bear_score floor 9 has WR 0.238, LOWER than
floor 7's 0.299 (LADDER-FULLHIST-2026-07-27). So conviction must be a NEW axis, not a
threshold on the old one.

DESIGN (Fable memo 2026-08-12, analysis/deep-research/2026-08-12-churn/
CONVICTION-RATCHET-DESIGN-2026-08-12.md):
  score 0-8, side-specific, from producers ALREADY on disk and already fresh.
  Gate = ESCALATING RATCHET: entry k of the day requires  floor + step*k.
  Defaults 4 / 1 -> 1st entry needs 4, 4th needs 7, 5th needs a perfect 8.
  The ratchet IS the sit-out: a day offering only conviction-3 signals is declined at k=0.

PURITY CONTRACT. This module performs NO I/O and NEVER raises. Every input is passed in by
the caller; every absent/unreadable input degrades that component to 0 and is named in
`degraded_components`, so a broken sensor can never silently suppress trading — worst case is
today's behaviour, loudly labelled. This mirrors exit_manager's pure-planner split.

DELIBERATELY NOT USED, with reasons (do not "improve" these in):
  * context_bundle.trend_alignment — its own Phase-1 correlation study graded it and KILLED it
    (context_bundle_producer.py:75).
  * ER30 / regime — frozen under prereg REGIME-CONDITIONAL-EXIT-2026-08-11, and 08-12's ER30
    of 0.79 is the HIGH bucket: a regime gate would have APPROVED the incident day.
  * ribbon state — the 2026-08-12 audit cleared the ribbon as a correct multi-hour trend
    gauge; conviction deliberately reads no ribbon so the two axes stay independent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

# Component weights. v0 DEFAULTS — the builder calibrates these on the two origin exhibits
# (the 38 fills of 2026-08-12 must mostly FAIL floor 4; J's 12:35 bounce + the edge-master
# source-of-truth winners must PASS) and then FREEZES them in a prereg before forward day 1.
W_NAMED_LEVEL = 2      # C1 — the only 2-pointer: no named level, no trade
W_MULTI_DAY = 1        # C2
W_FRESH_TEST = 1       # C3
W_RANGE_EXTREME = 1    # C4
W_STRUCTURE = 1        # C5
W_ELITE_TRIGGER = 1    # C6
W_ZONE_STACK = 1       # C7
MAX_SCORE = (W_NAMED_LEVEL + W_MULTI_DAY + W_FRESH_TEST + W_RANGE_EXTREME
             + W_STRUCTURE + W_ELITE_TRIGGER + W_ZONE_STACK)  # 8

LEVEL_MATCH_TOL = 0.25      # C1: entry level must match a named record within $0.25
MEMORY_SCORE_MIN = 40       # C2
MAX_PRIOR_TESTS_TODAY = 1   # C3: this is the 1st or 2nd test of the level today
RANGE_EXTREME_PCT = 0.30    # C4: top/bottom 30% of the prior-day-union-today envelope
ZONE_MIN_SOURCES = 3        # C7

# CALIBRATED 2026-08-12 on origin exhibit A, floor 4 -> 5. At 4, the identity components
# (C1 named +2, C2 remembered +1, C3 fresh +1) STACK EXACTLY TO THE FLOOR, so any named,
# remembered, lightly-tested level cleared the bar on level identity alone. 08-12's signature
# losing entry — BULLISH_RECLAIM at MEMORY_RES_225 (773.06, 139 touches) with trigger close
# 773.54 sitting at range position 0.601, i.e. NOWHERE NEAR an edge — scored exactly 4 and
# passed. Floor 5 makes level identity NECESSARY BUT NOT SUFFICIENT: a trade must also earn at
# least one point of CONTEXT (range location, structure agreement, elite trigger, or zone
# stack). J's 12:35 bounce scores 7-8 and is unaffected.
#
# CALIBRATION CANDIDATE for the prereg, deliberately NOT added here (adding a component now
# would be un-preregistered tuning on the very exhibit that motivated it): ROLE-SIDE COHERENCE
# — a call at a level whose role is `resistance` is a different trade from a call at `support`,
# and J reads exactly that ("we hit the same level and rejected it"). The records already carry
# `role`. Evaluate it as a C1 refinement when the weights are frozen, with its own exhibit.
DEFAULT_FLOOR = 5
DEFAULT_RATCHET_STEP = 1

_ELITE_TRIGGER_MARKERS = ("confluence", "sequence")


@dataclass(frozen=True)
class ConvictionResult:
    total: int
    components: dict = field(default_factory=dict)
    degraded_components: tuple = ()
    matched_level_label: Optional[str] = None
    matched_level_price: Optional[float] = None
    k: int = 0
    floor_effective: int = DEFAULT_FLOOR
    would_block: bool = False
    max_score: int = MAX_SCORE

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "max": self.max_score,
            "components": dict(self.components),
            "degraded_components": list(self.degraded_components),
            "matched_level_label": self.matched_level_label,
            "matched_level_price": self.matched_level_price,
            "k": self.k,
            "floor_effective": self.floor_effective,
            "would_block": self.would_block,
        }


def effective_floor(k: int, floor: int = DEFAULT_FLOOR,
                    step: int = DEFAULT_RATCHET_STEP) -> int:
    """The ESCALATING RATCHET. Entry k (0-indexed: k = entries already taken today) must
    clear floor + step*k. This is the sit-out mechanism — it spends the day's budget on
    QUALITY RANK rather than clock order, which is why it beats a flat trade cap (a flat
    cap on 2026-08-12 would have spent itself on the first two losers and been done before
    J's 12:35 bounce)."""
    try:
        return int(floor) + int(step) * max(0, int(k))
    except (TypeError, ValueError):
        return int(DEFAULT_FLOOR)


def _f(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None  # reject NaN


def _match_level(entry_level: Optional[float],
                 records: Optional[Sequence[Mapping[str, Any]]]):
    """C1 — find the NAMED, PROVENANCED record this entry is tied to.

    'If you can't name the level, there's no trade.' The blind trendline-only cohort (no
    named level) is measured at −$1,830 / WR 0.19 over n=124, and 89% of bear ENTERs came
    through that bypass. A bare float within $12 of spot is not a level; a record with a
    label and a touch history is."""
    lv = _f(entry_level)
    if lv is None or not records:
        return None
    best, best_d = None, None
    for rec in records:
        if not isinstance(rec, Mapping):
            continue
        p = _f(rec.get("price") or rec.get("level") or rec.get("value"))
        if p is None:
            continue
        d = abs(p - lv)
        if d <= LEVEL_MATCH_TOL and (best_d is None or d < best_d):
            best, best_d = rec, d
    return best


def score_conviction(
    *,
    side: str,
    entry_level: Optional[float],
    level_records: Optional[Sequence[Mapping[str, Any]]],
    triggers_fired: Optional[Sequence[str]] = None,
    level_states: Optional[Mapping[str, Any]] = None,
    trigger_close: Optional[float] = None,
    envelope_high: Optional[float] = None,
    envelope_low: Optional[float] = None,
    structure_side: Optional[str] = None,
    confluence_zones: Optional[Sequence[Mapping[str, Any]]] = None,
    k: int = 0,
    floor: int = DEFAULT_FLOOR,
    ratchet_step: int = DEFAULT_RATCHET_STEP,
) -> ConvictionResult:
    """Score one ENTER verdict. Pure. Never raises.

    side: 'C' (call/bullish) or 'P' (put/bearish).
    structure_side: 'C'/'P'/None — the sameday BOS/CHoCH read. None => degraded (C5 is a
      SOFT +1 and never a hard gate: the chop-defense battery showed blocking zero-structure
      entries costs Tuesday −$2,091, because early gap entries are always zero-structure).
    """
    comp: dict = {}
    degraded: list = []
    s = (side or "").upper()[:1]

    # --- C1 NAMED LEVEL (+2) -------------------------------------------------------------
    rec = _match_level(entry_level, level_records)
    if not level_records:
        degraded.append("named_level")
    comp["named_level"] = W_NAMED_LEVEL if rec is not None else 0
    label = str(rec.get("label")) if isinstance(rec, Mapping) and rec.get("label") else None
    price = _f(rec.get("price") or rec.get("level") or rec.get("value")) if rec else None

    # --- C2 MULTI-DAY MEMORY (+1) --------------------------------------------------------
    # Scores the LEVEL's history. Paired deliberately with C3, which scores the TEST's
    # freshness — C25/L142: high touch_count drives BOTH stars and eventual breaks, so we
    # reward a FRESH test OF a REMEMBERED level, never accumulation on its own.
    mem = 0
    if rec is not None:
        ms = _f(rec.get("memory_score"))
        if (ms is not None and ms >= MEMORY_SCORE_MIN) or rec.get("multi_day") \
                or str(rec.get("source", "")).startswith("shelf") \
                or str(rec.get("label", "")).startswith("MEMORY_"):
            mem = W_MULTI_DAY
    comp["multi_day_memory"] = mem

    # --- C3 FRESH TEST (+1) --------------------------------------------------------------
    fresh = 0
    if level_states is None:
        degraded.append("fresh_test")
    elif rec is not None and price is not None:
        st = None
        for key, val in (level_states or {}).items():
            kp = _f(key)
            if kp is not None and abs(kp - price) <= LEVEL_MATCH_TOL:
                st = val
                break
        hist = (st or {}).get("bounce_history") if isinstance(st, Mapping) else None
        n_prior = len(hist) if isinstance(hist, (list, tuple)) else 0
        if n_prior <= MAX_PRIOR_TESTS_TODAY:
            fresh = W_FRESH_TEST
    comp["fresh_test"] = fresh

    # --- C4 RANGE EXTREME (+1) -----------------------------------------------------------
    # Puts want the TOP of the envelope, calls the BOTTOM. This is the component that
    # distinguishes J's 12:35 bounce (a long at the range LOW) from the engine's 38 entries
    # (longs fired mid-flush and at the range TOP).
    rng = 0
    c, hi, lo = _f(trigger_close), _f(envelope_high), _f(envelope_low)
    if c is None or hi is None or lo is None or hi <= lo:
        degraded.append("range_extreme")
    else:
        pos = (c - lo) / (hi - lo)
        if s == "P" and pos >= (1.0 - RANGE_EXTREME_PCT):
            rng = W_RANGE_EXTREME
        elif s == "C" and pos <= RANGE_EXTREME_PCT:
            rng = W_RANGE_EXTREME
        comp["range_position"] = round(pos, 3)
    comp["range_extreme"] = rng

    # --- C5 STRUCTURE AGREEMENT (+1, SOFT) -----------------------------------------------
    if structure_side is None:
        degraded.append("structure")
        comp["structure_agreement"] = 0
    else:
        comp["structure_agreement"] = (
            W_STRUCTURE if str(structure_side).upper()[:1] == s else 0)

    # --- C6 ELITE TRIGGERS (+1) ----------------------------------------------------------
    tf = [str(t).lower() for t in (triggers_fired or [])]
    if not tf:
        degraded.append("elite_trigger")
    comp["elite_trigger"] = (
        W_ELITE_TRIGGER if any(m in t for t in tf for m in _ELITE_TRIGGER_MARKERS) else 0)

    # --- C7 ZONE STACK (+1) --------------------------------------------------------------
    zone = 0
    if confluence_zones is None:
        degraded.append("zone_stack")
    elif price is not None:
        for z in confluence_zones:
            if not isinstance(z, Mapping):
                continue
            zl, zh = _f(z.get("low") or z.get("zone_low")), _f(z.get("high") or z.get("zone_high"))
            n_src = _f(z.get("n_sources")) or 0
            if zl is not None and zh is not None and zl <= price <= zh and n_src >= ZONE_MIN_SOURCES:
                zone = W_ZONE_STACK
                break
    comp["zone_stack"] = zone

    total = sum(v for key, v in comp.items() if key != "range_position")
    fl = effective_floor(k, floor, ratchet_step)
    return ConvictionResult(
        total=int(total),
        components=comp,
        degraded_components=tuple(degraded),
        matched_level_label=label,
        matched_level_price=price,
        k=int(k),
        floor_effective=fl,
        would_block=bool(total < fl),
    )
