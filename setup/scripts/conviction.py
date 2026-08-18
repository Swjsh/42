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

# --- TRENDLINE ANCHOR (v2 variant, 2026-08-18) ---------------------------------------------
# WHY: two live days (08-17 +$360, 08-18 +$162) were won on `trendline_rejection`, and v0
# scored every one of them 0/8 -- 104 post-fix rows, 100% would_block, delta_if_armed -$522.
# The cause is structural, not tuning: C1 pays only for a NAMED HORIZONTAL level, and a
# trendline is a SLOPED line with no name, so the winner's `trigger_level_exact` is null.
# C4 compounds it -- "puts want the TOP of the envelope" scores a breakdown at the session
# low as bad location, which is exactly what a continuation entry IS.
#
# v2 therefore generalises TWO components rather than bolting on a 9th:
#   C1  "no named level, no trade"  ->  "no ANCHOR, no trade" (horizontal OR quality trendline)
#   C4  "range extreme"             ->  "good location" (range extreme OR AT the line)
# MAX_SCORE stays 8 so v0 and v2 floors are directly comparable in the A/B.
_SCORING_KEYS = ("named_level", "multi_day_memory", "fresh_test", "range_extreme",
                 "structure_agreement", "elite_trigger", "zone_stack")

TL_MIN_RESPECTS = 20        # a line the tape has actually honoured (today's winners: 52-124)
TL_MAX_VIOLATIONS = 6       # ...without being repeatedly sliced
TL_TOUCH_TOL = 0.60         # $: entry must be AT the line to earn C4-as-location
_TL_TRIGGER_MARKERS = ("trendline",)

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


def _match_trendline(side: str, close: Optional[float],
                     records: Optional[Sequence[Mapping[str, Any]]]) -> Optional[Mapping[str, Any]]:
    """The best QUALITY trendline this entry is trading against, or None. Pure.

    Quality bar = the tape has honoured it (respects >= TL_MIN_RESPECTS) without repeatedly
    slicing it (violations <= TL_MAX_VIOLATIONS). Side matters: a PUT trades a rejection at
    RESISTANCE / a break of SUPPORT, so both kinds qualify -- what must hold is that price is
    AT the line, which the caller's TL_TOUCH_TOL check enforces for C4. Deliberately does NOT
    filter on anchor_family: doctrine says a line is all-wick XOR all-body, never mixed, and
    the producer already guarantees that -- re-filtering here would silently halve the input.
    """
    if not records or close is None:
        return None
    best = None
    best_gap = None
    for r in records:
        if not isinstance(r, Mapping):
            continue
        val = _f(r.get("current_value") if r.get("current_value") is not None
                 else r.get("break_level"))
        if val is None:
            continue
        respects = r.get("respect_count")
        violations = r.get("violations")
        try:
            if int(respects) < TL_MIN_RESPECTS:
                continue
            if violations is not None and int(violations) > TL_MAX_VIOLATIONS:
                continue
        except (TypeError, ValueError):
            continue
        gap = abs(close - val)
        if best_gap is None or gap < best_gap:
            best, best_gap = r, gap
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
    trendline_records: Optional[Sequence[Mapping[str, Any]]] = None,
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
    # v2 ANCHOR GENERALISATION (opt-in: only when trendline_records is passed; absent =>
    # byte-identical v0, which keeps the running shadow series comparable).
    tl_rec = None
    tl_on = trendline_records is not None
    if tl_on:
        tf_probe = [str(t).lower() for t in (triggers_fired or [])]
        tl_fired = any(m in t for t in tf_probe for m in _TL_TRIGGER_MARKERS)
        tl_rec = _match_trendline(s, _f(trigger_close), trendline_records) if tl_fired else None
        comp["trendline_anchor"] = W_NAMED_LEVEL if tl_rec is not None else 0
        if tl_rec is not None:
            comp["trendline_respects"] = tl_rec.get("respect_count")
            comp["trendline_value"] = _f(tl_rec.get("current_value"))
        if comp["named_level"] == 0 and tl_rec is not None:
            comp["named_level"] = W_NAMED_LEVEL   # C1 satisfied by a SLOPED anchor
    label = str(rec.get("label")) if isinstance(rec, Mapping) and rec.get("label") else None
    price = _f(rec.get("price") or rec.get("level") or rec.get("value")) if rec else None

    # --- C2 MULTI-DAY MEMORY (+1) --------------------------------------------------------
    # Scores the LEVEL's history. Paired deliberately with C3, which scores the TEST's
    # freshness — C25/L142: high touch_count drives BOTH stars and eventual breaks, so we
    # reward a FRESH test OF a REMEMBERED level, never accumulation on its own.
    mem = 0
    if rec is not None:
        ms = _f(rec.get("memory_score"))
        # BUG FIX 2026-08-12 (found by the historical backtest): this tested
        # `source.startswith("shelf")`, but the producer writes `daily_context_shelf` — so the
        # highest-weighted level class in the compiler (SHELF, weight 5, multi-WEEK zones)
        # could NEVER score the memory component. A dead branch, C14 class, in code I shipped
        # the same night. Substring match, not prefix.
        if (ms is not None and ms >= MEMORY_SCORE_MIN) or rec.get("multi_day") \
                or "shelf" in str(rec.get("source", "")).lower() \
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
    # v2 LOCATION GENERALISATION: a trendline entry's "good location" is being AT THE LINE,
    # not at the envelope extreme. Without this, a breakdown rejection off a sloped line is
    # scored as bad location BY CONSTRUCTION -- the second half of why v0 zeroed the winners.
    if tl_on and rng == 0 and tl_rec is not None and c is not None:
        tl_val = _f(tl_rec.get("current_value"))
        if tl_val is not None and abs(c - tl_val) <= TL_TOUCH_TOL:
            rng = W_RANGE_EXTREME
            comp["location_source"] = "at_trendline"
            if "range_extreme" in degraded:
                degraded.remove("range_extreme")
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

    # EXPLICIT ALLOWLIST, not exclusion-by-one. v2 adds DIAGNOSTIC keys (trendline_anchor,
    # trendline_respects, trendline_value, location_source, range_position) that must never
    # reach the total -- trendline_anchor in particular MIRRORS the C1 point it already
    # granted, so summing it would double-count the anchor and inflate every trendline entry
    # by 2. An exclusion list would have silently mis-scored the moment a key was added.
    total = sum(int(comp.get(key) or 0) for key in _SCORING_KEYS)
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
