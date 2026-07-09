"""combinators.py — generic boolean/sequence glue for composing Predicates.

These are NOT domain primitives (they don't know about levels, VWAP, swings, ...); they
are the grammar's structural language features: AND / OR / NOT / "A within N bars after
B" / "chain a computed level into a break check". registry.py composes the 15 domain
predicates (predicates.py) using these 5 combinators to build every seeded PatternRule.

Predicate contract (shared with predicates.py): a Predicate is
`Callable[[PatternContext, int], Optional[dict]]`. `None` means "does not hold at bar t".
A dict (possibly empty) means "holds at bar t", and IS the evidence merged into the
eventual GrammarHit (see grammar.py::evaluate_rule). `bool(result)` is the operator's
truth value — that is the "boolean composition" the spec calls for; the dict payload
rides along for free.
"""
from __future__ import annotations

from typing import Callable, Optional

from .context import PatternContext

Predicate = Callable[[PatternContext, int], Optional[dict]]


def all_of(*preds: Predicate) -> Predicate:
    """AND — every predicate must hold. Evidence dicts are merged via dict.update() in
    argument order, so on a key collision (e.g. two sub-predicates both set
    "trigger_level") the LAST predicate in the argument list wins. Rules that rely on
    this (see registry.py's wedge_rising_into_resistance) say so inline.
    """
    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        evidence: dict = {}
        for pred in preds:
            r = pred(ctx, t)
            if r is None:
                return None
            evidence.update(r)
        return evidence
    return _p


def any_of(*preds: Predicate) -> Predicate:
    """OR — the first predicate (in argument order) that holds wins; its evidence is
    returned as-is (no merge with the others)."""
    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        for pred in preds:
            r = pred(ctx, t)
            if r is not None:
                return r
        return None
    return _p


def negate(pred: Predicate) -> Predicate:
    """NOT — holds (with empty evidence, since there is nothing positive to report)
    iff `pred` does NOT hold at bar t."""
    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        return {} if pred(ctx, t) is None else None
    return _p


def within_n_bars_after(*, later: Predicate, earlier: Predicate, n: int) -> Predicate:
    """SEQUENCE operator — "A within N bars after B": `later` (A) must hold AT bar t,
    and `earlier` (B) must have held at some bar s in [t-n, t] (s may equal t). B is the
    earlier event, A is the later one that follows within N bars — read the two
    parameter names, not the literal word order, to avoid the prose's ambiguity.

    Evidence = `later`'s dict, plus `sequence_anchor_bar_index`/`sequence_gap_bars`, plus
    `earlier`'s keys prefixed `anchor_` (never clobbers `later`'s own keys).
    """
    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        later_hit = later(ctx, t)
        if later_hit is None:
            return None
        lo = max(0, t - n)
        for s in range(t, lo - 1, -1):
            earlier_hit = earlier(ctx, s)
            if earlier_hit is None:
                continue
            out = dict(later_hit)
            out["sequence_anchor_bar_index"] = s
            out["sequence_gap_bars"] = t - s
            for k, v in earlier_hit.items():
                out.setdefault(f"anchor_{k}", v)
            return out
        return None
    return _p


def then_break(*, base: Predicate, side: str, require_cross: bool = True) -> Predicate:
    """Chain: `base` must hold at t AND supply a "trigger_level" key in its evidence;
    this additionally requires close[t] to have crossed THAT level this bar
    (side="above"|"below"). Threads a structurally-computed level (e.g. a flat_side
    cluster, or the latest price of a monotone_swings run) into a break check, which
    independent all_of() cannot do (its branches don't share data). Powers the
    triangle/rectangle/wedge family in registry.py.
    """
    if side not in ("above", "below"):
        raise ValueError("side must be 'above' or 'below'")

    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        r = base(ctx, t)
        if r is None or "trigger_level" not in r or r["trigger_level"] is None:
            return None
        level = r["trigger_level"]
        c0 = ctx.bars[t].close
        c1 = ctx.bars[t - 1].close if t >= 1 else None
        if side == "above":
            if not (c0 > level):
                return None
            if require_cross and not (c1 is not None and c1 <= level):
                return None
        else:
            if not (c0 < level):
                return None
            if require_cross and not (c1 is not None and c1 >= level):
                return None
        return r
    return _p
